#!/usr/bin/env python3
"""
Agnes MCP Server — agnes_image_video_mcp.py
=============================================
A Model Context Protocol server that wraps Agnes Image & Video APIs.

Tools exposed:
  - generate_image:  Text-to-image / image-to-image (agnes-image-2.1-flash)
  - generate_video:  Text-to-video / image-to-video (agnes-video-v2.0, async)
  - get_video_result: Poll for async video task result

Environment variables:
  AGNES_API_KEY  (required)  — Bearer token for Agnes API
  AGNES_IMAGE_MODEL (optional, default: agnes-image-2.1-flash)
  AGNES_VIDEO_MODEL (optional, default: agnes-video-v2.0)
"""

import asyncio
import base64
import json
import os
import sys
import time
import mimetypes
import traceback
import urllib.request
import urllib.error

from mcp.server import Server
from mcp.server.stdio import stdio_server
import mcp.types as types

# ── Configuration ────────────────────────────────────────────────────────────

API_BASE = "https://apihub.agnes-ai.com"
IMAGE_ENDPOINT = f"{API_BASE}/v1/images/generations"
VIDEO_CREATE_ENDPOINT = f"{API_BASE}/v1/videos"
VIDEO_POLL_ENDPOINT = f"{API_BASE}/agnesapi"

IMAGE_MODEL = os.environ.get("AGNES_IMAGE_MODEL", "agnes-image-2.1-flash")
VIDEO_MODEL = os.environ.get("AGNES_VIDEO_MODEL", "agnes-video-v2.0")
IMAGE_TIMEOUT = 360
VIDEO_CREATE_TIMEOUT = 120
VIDEO_POLL_TIMEOUT = 60

server = Server("agnes-mcp")


# ── Helpers ──────────────────────────────────────────────────────────────────

def _get_api_key():
    key = os.environ.get("AGNES_API_KEY", "")
    if not key:
        raise ValueError("AGNES_API_KEY environment variable is not set")
    return key


def _data_uri(path: str) -> str:
    """Encode a local image file as a data: URI."""
    mime, _ = mimetypes.guess_type(path)
    if mime is None:
        mime = "image/png"
    with open(path, "rb") as fh:
        b64 = base64.b64encode(fh.read()).decode("ascii")
    return f"data:{mime};base64,{b64}"


def _post_json(url: str, api_key: str, payload: dict, timeout: int) -> tuple[dict, float]:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    start = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body), time.time() - start
    except urllib.error.HTTPError as e:
        elapsed = time.time() - start
        err_body = ""
        try:
            err_body = e.read().decode("utf-8")
        except Exception:
            pass
        raise RuntimeError(f"HTTP {e.code} after {elapsed:.1f}s\nResponse: {err_body}") from e


def _get_json(url: str, api_key: str, timeout: int) -> tuple[dict, float]:
    req = urllib.request.Request(
        url,
        headers={"Authorization": f"Bearer {api_key}"},
        method="GET",
    )
    start = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body), time.time() - start
    except urllib.error.HTTPError as e:
        elapsed = time.time() - start
        err_body = ""
        try:
            err_body = e.read().decode("utf-8")
        except Exception:
            pass
        raise RuntimeError(f"HTTP {e.code} after {elapsed:.1f}s\nResponse: {err_body}") from e


# ── Tool Definitions ─────────────────────────────────────────────────────────

TOOLS = [
    types.Tool(
        name="generate_image",
        description=(
            "Generate an image using Agnes Image API (agnes-image-2.1-flash). "
            "Supports text-to-image and image-to-image (when input_image is provided). "
            "Returns the image URL."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "Image generation prompt"},
                "size": {"type": "string", "description": "Output size: '1K', '2K'", "default": "1K"},
                "ratio": {"type": "string", "description": "Aspect ratio: '1:1', '16:9', '9:16', '4:3'", "default": "1:1"},
                "input_image": {"type": "string", "description": "Local file path for image-to-image. If omitted, text-to-image."},
            },
            "required": ["prompt"],
        },
    ),
    types.Tool(
        name="generate_video",
        description=(
            "Create a video generation task using Agnes Video API (agnes-video-v2.0). "
            "ASYNC operation — returns task_id/video_id. "
            "Use get_video_result to poll for the completed video URL. "
            "Supports text-to-video and image-to-video (when image_url is provided)."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "Video content description"},
                "image_url": {"type": "string", "description": "Public URL of reference image for image-to-video."},
                "width": {"type": "integer", "description": "Video width (default 1152)", "default": 1152},
                "height": {"type": "integer", "description": "Video height (default 768)", "default": 768},
                "num_frames": {"type": "integer", "description": "Frames: 81≈3s, 121≈5s, 241≈10s. Must be 8n+1, max 441.", "default": 121},
                "frame_rate": {"type": "integer", "description": "Frame rate (1-60)", "default": 24},
                "negative_prompt": {"type": "string", "description": "What to avoid in the video"},
                "seed": {"type": "integer", "description": "Random seed for reproducibility"},
            },
            "required": ["prompt"],
        },
    ),
    types.Tool(
        name="get_video_result",
        description=(
            "Poll for the result of an async video generation task. "
            "Returns the video URL when completed. "
            "Call repeatedly until status is 'completed' or 'failed'."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "video_id": {"type": "string", "description": "The video_id from generate_video"},
            },
            "required": ["video_id"],
        },
    ),
]


# ── Request Handlers ─────────────────────────────────────────────────────────

async def _handle_list_tools(params) -> types.ListToolsResult:
    return types.ListToolsResult(tools=TOOLS)


async def _handle_call_tool(params: types.CallToolRequestParams) -> types.CallToolResult:
    name = params.name
    arguments = params.arguments or {}

    try:
        api_key = _get_api_key()
    except ValueError as e:
        return types.CallToolResult(
            content=[types.TextContent(type="text", text=f"[ERROR] {e}")],
            is_error=True,
        )

    if name == "generate_image":
        text = await _do_generate_image(api_key, arguments)
    elif name == "generate_video":
        text = await _do_generate_video(api_key, arguments)
    elif name == "get_video_result":
        text = await _do_get_video_result(api_key, arguments)
    else:
        return types.CallToolResult(
            content=[types.TextContent(type="text", text=f"[ERROR] Unknown tool: {name}")],
            is_error=True,
        )

    return types.CallToolResult(content=[types.TextContent(type="text", text=text)])


# ── Tool Implementations ─────────────────────────────────────────────────────

async def _do_generate_image(api_key: str, args: dict) -> str:
    prompt = args.get("prompt", "")
    size = args.get("size", "1K")
    ratio = args.get("ratio", "1:1")
    input_image = args.get("input_image")

    extra_body = {"response_format": "url"}
    if input_image:
        if not os.path.isfile(input_image):
            return f"[ERROR] input_image file not found: {input_image}"
        extra_body["image"] = _data_uri(input_image)

    payload = {
        "model": IMAGE_MODEL, "prompt": prompt, "size": size, "ratio": ratio,
        "extra_body": extra_body,
    }

    try:
        result, elapsed = await asyncio.to_thread(_post_json, IMAGE_ENDPOINT, api_key, payload, IMAGE_TIMEOUT)
    except Exception as e:
        return f"[ERROR] {e}"

    try:
        image_url = result["data"][0]["url"]
    except (KeyError, IndexError, TypeError):
        return f"[ERROR] Unexpected response\nElapsed: {elapsed:.1f}s\nResponse: {json.dumps(result, indent=2, ensure_ascii=False)}"

    mode = "image-to-image" if input_image else "text-to-image"
    return f"[OK] {mode} completed in {elapsed:.1f}s\nModel: {IMAGE_MODEL}\nSize: {size}  Ratio: {ratio}\nImage URL: {image_url}"


async def _do_generate_video(api_key: str, args: dict) -> str:
    prompt = args.get("prompt", "")
    image_url = args.get("image_url")
    width = args.get("width", 1152)
    height = args.get("height", 768)
    num_frames = args.get("num_frames", 121)
    frame_rate = args.get("frame_rate", 24)
    negative_prompt = args.get("negative_prompt")
    seed = args.get("seed")

    payload = {
        "model": VIDEO_MODEL, "prompt": prompt,
        "width": width, "height": height,
        "num_frames": num_frames, "frame_rate": frame_rate,
    }
    if image_url:
        payload["image"] = image_url
    if negative_prompt:
        payload["negative_prompt"] = negative_prompt
    if seed is not None:
        payload["seed"] = seed

    try:
        result, elapsed = await asyncio.to_thread(_post_json, VIDEO_CREATE_ENDPOINT, api_key, payload, VIDEO_CREATE_TIMEOUT)
    except Exception as e:
        return f"[ERROR] {e}"

    video_id = result.get("video_id") or result.get("task_id") or result.get("id")
    if not video_id:
        return f"[ERROR] No video_id in response\nResponse: {json.dumps(result, indent=2, ensure_ascii=False)}"

    mode = "image-to-video" if image_url else "text-to-video"
    return (
        f"[OK] {mode} task created in {elapsed:.1f}s\n"
        f"Model: {VIDEO_MODEL}\n"
        f"Video ID: {video_id}\n"
        f"Status: {result.get('status', 'unknown')}\n"
        f"Duration: {result.get('seconds', '?')}s\n"
        f"Size: {result.get('size', '?')}\n\n"
        f"Next: call get_video_result with video_id='{video_id}'"
    )


async def _do_get_video_result(api_key: str, args: dict) -> str:
    video_id = args.get("video_id", "")
    if not video_id:
        return "[ERROR] video_id is required"

    url = f"{VIDEO_POLL_ENDPOINT}?video_id={video_id}"
    try:
        result, elapsed = await asyncio.to_thread(_get_json, url, api_key, VIDEO_POLL_TIMEOUT)
    except Exception as e:
        return f"[ERROR] {e}"

    status = result.get("status", "unknown")
    progress = result.get("progress", 0)

    if status == "completed":
        video_url = result.get("url") or result.get("metadata", {}).get("url")
        if video_url:
            return f"[COMPLETED] Video ready! (polled in {elapsed:.1f}s)\nVideo URL: {video_url}\nDuration: {result.get('seconds', '?')}s\nSize: {result.get('size', '?')}"
        else:
            return f"[COMPLETED] No URL in response\nResponse: {json.dumps(result, indent=2, ensure_ascii=False)}"
    elif status == "failed":
        return f"[FAILED] {result.get('error', 'unknown')}\nResponse: {json.dumps(result, indent=2, ensure_ascii=False)}"
    else:
        return f"[{status.upper()}] Progress: {progress}%  (polled in {elapsed:.1f}s)\nVideo ID: {video_id}\nCall get_video_result again to continue polling."


# ── Register Handlers ────────────────────────────────────────────────────────

server.add_request_handler("tools/list", types.PaginatedRequestParams, _handle_list_tools)
server.add_request_handler("tools/call", types.CallToolRequestParams, _handle_call_tool)


# ── Main ─────────────────────────────────────────────────────────────────────

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
