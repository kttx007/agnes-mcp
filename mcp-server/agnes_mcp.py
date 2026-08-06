#!/usr/bin/env python3
"""
Agnes MCP Server (Enhanced) — agnes_mcp.py
============================================
Unified MCP server integrating features from:
  - kttx007/agnes-mcp (MCP protocol layer, MIT)
  - 1038lab/Agnes-AI (auto-translate, auto-upload, auto-poll, keyframes, compose, GPL v3 inspired)
  - jomeswang/agnes-ai-skill (prompt patterns, MIT inspired)

Tools (5):
  generate_image       — text2img / img2img / compose, with auto-translate
  generate_video       — text2video / img2video / keyframes, with auto-translate + auto-poll
  get_video_result     — poll for async video result, optional download
  translate_prompt     — translate non-English prompt to English via agnes-2.0-flash
  upload_media         — upload local file to Litterbox for URL-based operations

Environment:
  AGNES_API_KEY        (required)
  AGNES_IMAGE_MODEL    (default: agnes-image-2.1-flash)
  AGNES_VIDEO_MODEL    (default: agnes-video-v2.0)
  AGNES_TEXT_MODEL     (default: agnes-2.0-flash)
"""

import asyncio
import base64
import json
import mimetypes
import os
import sys
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request

from mcp.server import Server
from mcp.server.stdio import stdio_server
import mcp.types as types

# ── Config ───────────────────────────────────────────────────────────────────

API_BASE = os.environ.get("AGNES_API_BASE", "https://apihub.agnes-ai.com")
IMAGE_ENDPOINT = f"{API_BASE}/v1/images/generations"
VIDEO_CREATE = f"{API_BASE}/v1/videos"
VIDEO_POLL = f"{API_BASE}/agnesapi"
CHAT_ENDPOINT = f"{API_BASE}/v1/chat/completions"
LITTERBOX_URL = "https://litterbox.catbox.moe/resources/internals/api.php"

IMAGE_MODEL = os.environ.get("AGNES_IMAGE_MODEL", "agnes-image-2.1-flash")
VIDEO_MODEL = os.environ.get("AGNES_VIDEO_MODEL", "agnes-video-v2.0")
TEXT_MODEL = os.environ.get("AGNES_TEXT_MODEL", "agnes-2.0-flash")

server = Server("agnes-mcp")


# ── HTTP Helpers ──────────────────────────────────────────────────────────────

def _get_key():
    key = os.environ.get("AGNES_API_KEY", "")
    if not key:
        raise ValueError("AGNES_API_KEY not set")
    return key


def _post_json(url, payload, timeout=360):
    key = _get_key()
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST",
    )
    start = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8")), time.time() - start
    except urllib.error.HTTPError as e:
        elapsed = time.time() - start
        body = ""
        try:
            body = e.read().decode("utf-8")
        except Exception:
            pass
        raise RuntimeError(f"HTTP {e.code} after {elapsed:.1f}s\nResponse: {body}")


def _get_json(url, timeout=60):
    key = _get_key()
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {key}"}, method="GET")
    start = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8")), time.time() - start
    except urllib.error.HTTPError as e:
        elapsed = time.time() - start
        body = ""
        try:
            body = e.read().decode("utf-8")
        except Exception:
            pass
        raise RuntimeError(f"HTTP {e.code} after {elapsed:.1f}s\nResponse: {body}")


# ── Feature: Auto-Translate (ported from 1038lab/translate.py) ───────────────

def _needs_translation(text):
    return any(ord(c) > 127 for c in text)


async def _translate_prompt(prompt):
    """Translate non-English prompt to English via agnes-2.0-flash."""
    if not _needs_translation(prompt):
        return prompt
    payload = {
        "model": TEXT_MODEL,
        "messages": [
            {"role": "system", "content": "Translate the following prompt to English. Preserve all visual details, style, lighting, composition, and quality terms. Return ONLY the translated text, no explanation."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.3,
        "max_tokens": 1024,
    }
    try:
        result, elapsed = await asyncio.to_thread(_post_json, CHAT_ENDPOINT, payload, 30)
        return result["choices"][0]["message"]["content"]
    except Exception:
        return prompt  # fallback to original on error


# ── Feature: Media Upload (ported from 1038lab/media.py) ─────────────────────

def _file_to_base64(path):
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("ascii")


def _data_uri(path):
    mime, _ = mimetypes.guess_type(path)
    if mime is None:
        mime = "image/png"
    return f"data:{mime};base64,{_file_to_base64(path)}"


def _upload_to_litterbox(file_path, ttl="1h"):
    """Upload local file to Litterbox and return public URL."""
    boundary = "----AgnesMediaBoundary"
    filename = os.path.basename(file_path)
    with open(file_path, "rb") as f:
        file_data = f.read()
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="reqtype"\r\n\r\nfileupload\r\n'
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="time"\r\n\r\n{ttl}\r\n'
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="fileToUpload"; filename="{filename}"\r\n'
        f"Content-Type: {mimetypes.guess_type(filename)[0] or 'application/octet-stream'}\r\n\r\n"
    ).encode() + file_data + f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(
        LITTERBOX_URL, data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    return urllib.request.urlopen(req).read().decode().strip()


def _resolve_image(path_or_url):
    """Return URL if already URL; upload to Litterbox if local path."""
    if path_or_url.startswith(("http://", "https://")):
        return path_or_url
    if os.path.isfile(path_or_url):
        return _upload_to_litterbox(path_or_url)
    raise FileNotFoundError(f"File not found: {path_or_url}")


# ── Feature: Video Auto-Poll (ported from 1038lab/video.py) ──────────────────

async def _poll_video(video_id, max_wait=600, interval=10):
    """Poll until video is completed or failed. Returns result dict."""
    start = time.time()
    while True:
        if time.time() - start > max_wait:
            return {"video_id": video_id, "status": "timed_out", "elapsed": max_wait}
        url = f"{VIDEO_POLL}?video_id={video_id}&model_name={VIDEO_MODEL}"
        try:
            result, elapsed = await asyncio.to_thread(_get_json, url, 60)
        except Exception:
            await asyncio.sleep(interval)
            continue
        status = result.get("status", "unknown")
        progress = result.get("progress", 0)
        if status in ("completed", "succeeded", "done"):
            video_url = result.get("url") or result.get("video_url") or result.get("metadata", {}).get("url")
            return {"video_id": video_id, "status": "completed", "video_url": video_url,
                    "elapsed": round(time.time() - start, 1), "result": result}
        elif status in ("failed", "error"):
            return {"video_id": video_id, "status": "failed",
                    "error": result.get("error", "unknown"), "result": result}
        await asyncio.sleep(interval)


# ── Tool Definitions ─────────────────────────────────────────────────────────

TOOLS = [
    types.Tool(
        name="generate_image",
        description=(
            "Generate an image via Agnes Image API. Supports text2img, img2img, and compose (multiple images). "
            "Auto-translates non-English prompts to English. Returns image URL(s)."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "Image prompt (auto-translated if non-English)"},
                "mode": {"type": "string", "enum": ["text2img", "img2img", "compose"],
                         "default": "text2img", "description": "text2img, img2img (1 ref image), compose (2+ images)"},
                "images": {"type": "array", "items": {"type": "string"},
                           "description": "Local file paths or URLs for img2img/compose"},
                "size": {"type": "string", "default": "1K", "description": "1K or 2K"},
                "ratio": {"type": "string", "default": "1:1", "description": "1:1, 16:9, 9:16, 4:3"},
                "auto_translate": {"type": "boolean", "default": True, "description": "Auto-translate non-English prompts"},
            },
            "required": ["prompt"],
        },
    ),
    types.Tool(
        name="generate_video",
        description=(
            "Create a video generation task via Agnes Video API. Supports text2video, img2video, and keyframes. "
            "Auto-translates prompts. Optional auto-poll waits for completion and returns the video URL."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "Video prompt (auto-translated if non-English)"},
                "mode": {"type": "string", "enum": ["text2video", "img2video", "keyframes"],
                         "default": "text2video"},
                "images": {"type": "array", "items": {"type": "string"},
                           "description": "Image URLs for img2video (1) or keyframes (2+)"},
                "width": {"type": "integer", "default": 1152},
                "height": {"type": "integer", "default": 768},
                "num_frames": {"type": "integer", "default": 121, "description": "8n+1 rule: 81=3s, 121=5s, 241=10s"},
                "frame_rate": {"type": "integer", "default": 24},
                "negative_prompt": {"type": "string"},
                "seed": {"type": "integer"},
                "auto_translate": {"type": "boolean", "default": True},
                "auto_poll": {"type": "boolean", "default": False, "description": "Wait for completion (up to 600s)"},
            },
            "required": ["prompt"],
        },
    ),
    types.Tool(
        name="get_video_result",
        description="Poll for async video task result. Returns video URL when completed.",
        inputSchema={
            "type": "object",
            "properties": {
                "video_id": {"type": "string"},
            },
            "required": ["video_id"],
        },
    ),
    types.Tool(
        name="translate_prompt",
        description="Translate a non-English prompt to English using Agnes text model. Returns English prompt.",
        inputSchema={
            "type": "object",
            "properties": {"prompt": {"type": "string"}},
            "required": ["prompt"],
        },
    ),
    types.Tool(
        name="upload_media",
        description="Upload a local file to Litterbox and return a public URL. Useful for img2img/img2video/keyframes.",
        inputSchema={
            "type": "object",
            "properties": {"file_path": {"type": "string"}, "ttl": {"type": "string", "default": "1h", "description": "1h, 12h, 24h, 72h"}},
            "required": ["file_path"],
        },
    ),
]


# ── Handlers ─────────────────────────────────────────────────────────────────

async def _handle_list_tools(params) -> types.ListToolsResult:
    return types.ListToolsResult(tools=TOOLS)


async def _handle_call_tool(params: types.CallToolRequestParams) -> types.CallToolResult:
    name = params.name
    args = params.arguments or {}
    try:
        api_key = _get_key()
    except ValueError as e:
        return types.CallToolResult(content=[types.TextContent(type="text", text=f"[ERROR] {e}")], is_error=True)

    handlers = {
        "generate_image": _do_generate_image,
        "generate_video": _do_generate_video,
        "get_video_result": _do_get_video_result,
        "translate_prompt": _do_translate,
        "upload_media": _do_upload,
    }
    handler = handlers.get(name)
    if not handler:
        return types.CallToolResult(content=[types.TextContent(type="text", text=f"[ERROR] Unknown tool: {name}")], is_error=True)
    text = await handler(args)
    return types.CallToolResult(content=[types.TextContent(type="text", text=text)])


async def _do_generate_image(args):
    prompt = args.get("prompt", "")
    mode = args.get("mode", "text2img")
    images = args.get("images", [])
    size = args.get("size", "1K")
    ratio = args.get("ratio", "1:1")
    auto_translate = args.get("auto_translate", True)

    if auto_translate:
        prompt = await _translate_prompt(prompt)

    extra_body = {"response_format": "url"}
    if mode in ("img2img", "compose") and images:
        urls = []
        for img in images:
            try:
                urls.append(await asyncio.to_thread(_resolve_image, img))
            except Exception as e:
                return f"[ERROR] Failed to resolve image {img}: {e}"
        extra_body["image"] = urls if mode == "compose" else urls[0]

    payload = {"model": IMAGE_MODEL, "prompt": prompt, "size": size, "ratio": ratio, "extra_body": extra_body}
    try:
        result, elapsed = await asyncio.to_thread(_post_json, IMAGE_ENDPOINT, payload, 360)
    except Exception as e:
        return f"[ERROR] {e}"

    try:
        items = result.get("data", [])
        urls = [item["url"] for item in items if item.get("url")]
    except (KeyError, TypeError):
        return f"[ERROR] Unexpected response\n{json.dumps(result, indent=2, ensure_ascii=False)}"

    return f"[OK] {mode} in {elapsed:.1f}s\nModel: {IMAGE_MODEL}\nSize: {size}  Ratio: {ratio}\nImage URL(s):\n" + "\n".join(urls)


async def _do_generate_video(args):
    prompt = args.get("prompt", "")
    mode = args.get("mode", "text2video")
    images = args.get("images", [])
    width = args.get("width", 1152)
    height = args.get("height", 768)
    num_frames = args.get("num_frames", 121)
    frame_rate = args.get("frame_rate", 24)
    negative_prompt = args.get("negative_prompt")
    seed = args.get("seed")
    auto_translate = args.get("auto_translate", True)
    auto_poll = args.get("auto_poll", False)

    if auto_translate:
        prompt = await _translate_prompt(prompt)

    payload = {"model": VIDEO_MODEL, "prompt": prompt, "width": width, "height": height,
               "num_frames": num_frames, "frame_rate": frame_rate}
    if mode == "img2video" and images:
        url = await asyncio.to_thread(_resolve_image, images[0])
        payload["image"] = url
    elif mode == "keyframes" and len(images) >= 2:
        urls = [await asyncio.to_thread(_resolve_image, img) for img in images]
        payload["extra_body"] = {"image": urls, "mode": "keyframes"}
    if negative_prompt:
        payload["negative_prompt"] = negative_prompt
    if seed is not None:
        payload["seed"] = seed

    try:
        result, elapsed = await asyncio.to_thread(_post_json, VIDEO_CREATE, payload, 120)
    except Exception as e:
        return f"[ERROR] {e}"

    video_id = result.get("video_id") or result.get("task_id") or result.get("id")
    if not video_id:
        return f"[ERROR] No video_id\n{json.dumps(result, indent=2, ensure_ascii=False)}"

    if auto_poll:
        poll_result = await _poll_video(video_id, max_wait=600, interval=10)
        if poll_result["status"] == "completed":
            return f"[COMPLETED] {mode} in {poll_result['elapsed']:.1f}s\nVideo URL: {poll_result['video_url']}\nDuration: {result.get('seconds', '?')}s"
        elif poll_result["status"] == "failed":
            return f"[FAILED] {poll_result.get('error', 'unknown')}"
        else:
            return f"[TIMEOUT] Video ID: {video_id}\nCall get_video_result to check later."

    return f"[OK] {mode} task created in {elapsed:.1f}s\nVideo ID: {video_id}\nStatus: {result.get('status', 'unknown')}\nDuration: {result.get('seconds', '?')}s\nNext: call get_video_result with video_id='{video_id}'"


async def _do_get_video_result(args):
    video_id = args.get("video_id", "")
    if not video_id:
        return "[ERROR] video_id required"
    url = f"{VIDEO_POLL}?video_id={video_id}&model_name={VIDEO_MODEL}"
    try:
        result, elapsed = await asyncio.to_thread(_get_json, url, 60)
    except Exception as e:
        return f"[ERROR] {e}"
    status = result.get("status", "unknown")
    if status in ("completed", "succeeded", "done"):
        video_url = result.get("url") or result.get("video_url") or result.get("metadata", {}).get("url")
        return f"[COMPLETED] Video ready! (polled in {elapsed:.1f}s)\nVideo URL: {video_url}\nDuration: {result.get('seconds', '?')}s\nSize: {result.get('size', '?')}"
    elif status in ("failed", "error"):
        return f"[FAILED] {result.get('error', 'unknown')}"
    else:
        return f"[{status.upper()}] Progress: {result.get('progress', 0)}%  (polled in {elapsed:.1f}s)\nCall get_video_result again to continue polling."


async def _do_translate(args):
    prompt = args.get("prompt", "")
    translated = await _translate_prompt(prompt)
    if translated == prompt:
        return f"[INFO] Prompt is already English, no translation needed.\n{prompt}"
    return f"[OK] Translated:\n{translated}"


async def _do_upload(args):
    file_path = args.get("file_path", "")
    ttl = args.get("ttl", "1h")
    if not os.path.isfile(file_path):
        return f"[ERROR] File not found: {file_path}"
    try:
        url = await asyncio.to_thread(_upload_to_litterbox, file_path, ttl)
    except Exception as e:
        return f"[ERROR] Upload failed: {e}"
    return f"[OK] Uploaded to Litterbox (TTL: {ttl})\nURL: {url}"


# ── Register & Run ───────────────────────────────────────────────────────────

server.add_request_handler("tools/list", types.PaginatedRequestParams, _handle_list_tools)
server.add_request_handler("tools/call", types.CallToolRequestParams, _handle_call_tool)

async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"[FATAL] {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)
