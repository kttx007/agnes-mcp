#!/usr/bin/env python3
"""
Agnes MCP Server — agnes_mcp.py
================================
MCP server for Agnes AI image & video generation.

Tools (5):
  generate_image       — text2img / img2img / compose, with auto-translate
  generate_video       — text2video / img2video / multivideo / keyframes, auto-translate + optional auto-poll
  get_video_result     — poll an async video task, optional download
  translate_prompt     — translate a non-English prompt to English via agnes-2.0-flash
  upload_media         — upload a local file to a temporary host and return a public URL

Request shapes follow the official agnes-ai-cli (npm, v0.1.x):
  POST {base}/v1/images/generations   {model, prompt, size?, seed?, extra_body?: {image: [url...], response_format}}
  POST {base}/v1/videos               {model, prompt, width, height, num_frames, frame_rate, image? | extra_body?}
  GET  {base}/agnesapi?video_id=...   (video_xxx ids)
  GET  {base}/v1/videos/{task_id}     (task_xxx ids)

Environment:
  AGNES_API_KEY        (required; may also be put in a git-ignored .env file)
  AGNES_API_BASE       (default: https://apihub.agnes-ai.com)
  AGNES_IMAGE_MODEL    (default: agnes-image-2.1-flash)
  AGNES_VIDEO_MODEL    (default: agnes-video-v2.0)
  AGNES_TEXT_MODEL     (default: agnes-2.0-flash)
  AGNES_OUTPUT_DIR     (default: ./agnes-output, used when saving b64 images / downloading videos)
"""

import asyncio
import base64
import json
import mimetypes
import os
import re
import sys
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request

from mcp.server import Server
from mcp.server.stdio import stdio_server
import mcp.types as types


# ── .env loading (never overrides real environment variables) ────────────────

def _load_dotenv():
    here = os.path.dirname(os.path.abspath(__file__))
    for path in (os.path.join(here, ".env"), os.path.join(os.path.dirname(here), ".env")):
        if not os.path.isfile(path):
            continue
        try:
            with open(path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    k = k.strip().removeprefix("export ").strip()
                    v = v.strip().strip('"').strip("'")
                    if k and k not in os.environ:
                        os.environ[k] = v
        except OSError:
            pass


_load_dotenv()

# ── Config ───────────────────────────────────────────────────────────────────

API_BASE = os.environ.get("AGNES_API_BASE", "https://apihub.agnes-ai.com").rstrip("/")
if API_BASE.endswith("/v1"):
    API_BASE = API_BASE[:-3]
IMAGE_ENDPOINT = f"{API_BASE}/v1/images/generations"
VIDEO_CREATE = f"{API_BASE}/v1/videos"
VIDEO_POLL = f"{API_BASE}/agnesapi"
CHAT_ENDPOINT = f"{API_BASE}/v1/chat/completions"
LITTERBOX_URL = "https://litterbox.catbox.moe/resources/internals/api.php"
TMPFILES_URL = "https://tmpfiles.org/api/v1/upload"

IMAGE_MODEL = os.environ.get("AGNES_IMAGE_MODEL", "agnes-image-2.1-flash")
VIDEO_MODEL = os.environ.get("AGNES_VIDEO_MODEL", "agnes-video-v2.0")
TEXT_MODEL = os.environ.get("AGNES_TEXT_MODEL", "agnes-2.0-flash")
OUTPUT_DIR = os.environ.get("AGNES_OUTPUT_DIR", os.path.join(os.getcwd(), "agnes-output"))

IMAGE_MODELS = ["agnes-image-2.1-flash", "agnes-image-2.0-flash"]
TTL_CHOICES = ["1h", "12h", "24h", "72h"]
TTL_SECONDS = {"1h": "3600", "12h": "43200", "24h": "86400", "72h": "259200"}

# Pixel sizes for the legacy "1K"/"2K" + ratio shorthand.
_RATIO_SIZES = {
    "1K": {"1:1": "1024x1024", "16:9": "1344x768", "9:16": "768x1344", "4:3": "1152x864",
           "3:4": "864x1152", "3:2": "1216x832", "2:3": "832x1216"},
    "2K": {"1:1": "2048x2048", "16:9": "2560x1440", "9:16": "1440x2560", "4:3": "2304x1728",
           "3:4": "1728x2304", "3:2": "2432x1664", "2:3": "1664x2432"},
}


class AgnesError(Exception):
    pass


# ── HTTP Helpers ──────────────────────────────────────────────────────────────

def _get_key():
    key = (os.environ.get("AGNES_API_KEY") or os.environ.get("AGNES_API_TOKEN")
           or os.environ.get("APIHUB_AGNES_API_KEY") or "").strip()
    if not key:
        raise AgnesError(
            "AGNES_API_KEY not set. Create a key at https://platform.agnes-ai.com/settings/apiKeys "
            "and set it in your MCP client's env block (or a local, git-ignored .env file).")
    return key


def _redact(text):
    text = re.sub(r"\bBearer\s+[^\s\"'<]+", "Bearer [REDACTED]", text, flags=re.I)
    return re.sub(r"\bsk-[A-Za-z0-9_-]+", "[REDACTED]", text)


def _request(method, url, payload=None, timeout=360):
    """Return (status, parsed_body, elapsed). Raises AgnesError on network errors."""
    headers = {"Authorization": f"Bearer {_get_key()}", "Accept": "application/json"}
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    start = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status, raw = resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        status = e.code
        try:
            raw = e.read().decode("utf-8", "replace")
        except Exception:
            raw = ""
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise AgnesError(f"Network error calling {url}: {e}")
    elapsed = time.time() - start
    try:
        body = json.loads(raw) if raw.strip() else None
    except json.JSONDecodeError:
        body = raw
    return status, body, elapsed


def _fmt_body(body):
    if isinstance(body, (dict, list)):
        return _redact(json.dumps(body, indent=2, ensure_ascii=False))[:2000]
    return _redact(str(body))[:2000]


def _post_json(url, payload, timeout=360):
    status, body, elapsed = _request("POST", url, payload, timeout)
    if not 200 <= status < 300:
        raise AgnesError(f"HTTP {status} after {elapsed:.1f}s from {url}\nResponse: {_fmt_body(body)}")
    if not isinstance(body, dict):
        raise AgnesError(f"Non-JSON response from {url}: {_fmt_body(body)}")
    return body, elapsed


# ── Auto-Translate ───────────────────────────────────────────────────────────

def _needs_translation(text):
    return any(ord(c) > 127 for c in text)


async def _translate_prompt(prompt):
    """Translate a non-English prompt to English. Falls back to the original on error."""
    if not prompt or not _needs_translation(prompt):
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
        result, _ = await asyncio.to_thread(_post_json, CHAT_ENDPOINT, payload, 60)
        text = (result["choices"][0]["message"]["content"] or "").strip()
        return text or prompt
    except Exception:
        return prompt


# ── Media Upload ─────────────────────────────────────────────────────────────

def _multipart(fields, file_field, file_path):
    boundary = f"----AgnesMediaBoundary{int(time.time() * 1000)}"
    filename = os.path.basename(file_path)
    mime = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    with open(file_path, "rb") as f:
        file_data = f.read()
    parts = []
    for k, v in fields.items():
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
    parts.append(
        f'--{boundary}\r\nContent-Disposition: form-data; name="{file_field}"; filename="{filename}"\r\n'
        f"Content-Type: {mime}\r\n\r\n".encode() + file_data + b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


def _post_form(url, body, content_type, timeout=120):
    req = urllib.request.Request(url, data=body, method="POST",
                                 headers={"Content-Type": content_type, "User-Agent": "agnes-mcp/1.1"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", "replace").strip()


def _upload_litterbox(file_path, ttl):
    body, ctype = _multipart({"reqtype": "fileupload", "time": ttl}, "fileToUpload", file_path)
    text = _post_form(LITTERBOX_URL, body, ctype)
    if not re.match(r"^https?://", text):
        raise AgnesError(f"Litterbox did not return a URL: {text[:200]}")
    return text


def _upload_tmpfiles(file_path, ttl):
    body, ctype = _multipart({"expire": TTL_SECONDS.get(ttl, "3600")}, "file", file_path)
    data = json.loads(_post_form(TMPFILES_URL, body, ctype))
    url = (data.get("data") or {}).get("url", "")
    if not re.match(r"^https?://", url):
        raise AgnesError(f"tmpfiles did not return a URL: {data}")
    p = urllib.parse.urlparse(url)
    if p.hostname == "tmpfiles.org" and not p.path.startswith("/dl/"):
        url = urllib.parse.urlunparse(p._replace(path="/dl" + p.path))
    return url


def _upload_media(file_path, ttl="1h"):
    """Upload a local file to a temporary public host. Tries Litterbox, then tmpfiles."""
    if ttl not in TTL_CHOICES:
        ttl = "1h"
    failures = []
    for name, fn in (("Litterbox", _upload_litterbox), ("tmpfiles", _upload_tmpfiles)):
        try:
            return fn(file_path, ttl)
        except Exception as e:
            failures.append(f"{name}: {e}")
    raise AgnesError("Temporary upload failed: " + "; ".join(failures))


def _resolve_image(path_or_url, ttl="1h"):
    """Return a public URL: pass through http(s) URLs, upload local files and data URIs."""
    s = (path_or_url or "").strip()
    if s.startswith(("http://", "https://")):
        return s
    if s.startswith("data:"):
        m = re.match(r"^data:([^;,]+)?;base64,(.*)$", s, re.S)
        if not m:
            raise AgnesError("Malformed data URI (expected base64)")
        ext = mimetypes.guess_extension(m.group(1) or "image/png") or ".png"
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        tmp = os.path.join(OUTPUT_DIR, f"upload_{int(time.time() * 1000)}{ext}")
        with open(tmp, "wb") as f:
            f.write(base64.b64decode(m.group(2)))
        try:
            return _upload_media(tmp, ttl)
        finally:
            try:
                os.remove(tmp)
            except OSError:
                pass
    path = os.path.expanduser(s)
    if os.path.isfile(path):
        return _upload_media(path, ttl)
    raise AgnesError(f"Image not found (expected an http(s) URL, data URI, or existing local file): {s}")


async def _resolve_images(images, ttl="1h"):
    cache, out = {}, []
    for img in images:
        if img not in cache:
            cache[img] = await asyncio.to_thread(_resolve_image, img, ttl)
        out.append(cache[img])
    return out


# ── Image helpers ────────────────────────────────────────────────────────────

def _normalize_size(size, ratio):
    """Accept 'WxH' directly; map legacy '1K'/'2K' + ratio to pixels. Returns None to omit."""
    if not size and not ratio:
        return None
    size = (size or "1K").strip()
    if re.fullmatch(r"\d{2,5}\s*[xX*]\s*\d{2,5}", size):
        w, h = re.split(r"\s*[xX*]\s*", size)
        return f"{int(w)}x{int(h)}"
    tier = size.upper()
    if tier not in _RATIO_SIZES:
        raise AgnesError(f"Invalid size '{size}'. Use WIDTHxHEIGHT (e.g. 1024x1024) or 1K/2K with ratio.")
    ratio = (ratio or "1:1").strip()
    if ratio not in _RATIO_SIZES[tier]:
        raise AgnesError(f"Invalid ratio '{ratio}'. Supported: {', '.join(_RATIO_SIZES[tier])}")
    return _RATIO_SIZES[tier][ratio]


def _save_b64_image(b64):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    path = os.path.join(OUTPUT_DIR, f"agnes_img_{int(time.time() * 1000)}.png")
    with open(path, "wb") as f:
        f.write(base64.b64decode(b64))
    return path


def _extract_images(result):
    """Return list of URLs / saved file paths from an images/generations response."""
    out = []
    data = result.get("data")
    if isinstance(data, dict):
        data = [data]
    for item in data or []:
        if not isinstance(item, dict):
            continue
        if isinstance(item.get("url"), str) and item["url"]:
            out.append(item["url"])
        elif isinstance(item.get("b64_json"), str) and item["b64_json"]:
            out.append(_save_b64_image(item["b64_json"]))
    if not out and isinstance(result.get("url"), str):
        out.append(result["url"])
    return out


# ── Video helpers ────────────────────────────────────────────────────────────

def _normalize_status(record):
    raw = record.get("status") or record.get("state")
    raw = raw.lower() if isinstance(raw, str) else None
    if raw in ("succeeded", "success", "completed", "complete", "done", "finished"):
        return "completed"
    if raw in ("failed", "error", "failure"):
        return "failed"
    if raw in ("cancelled", "canceled"):
        return "canceled"
    if raw in ("in_progress", "processing", "running", "generating"):
        return "in_progress"
    if raw is None and record.get("completed_at") is not None and _extract_video_url(record):
        return "completed"
    return "queued"


def _extract_video_url(record):
    meta = record.get("metadata") if isinstance(record.get("metadata"), dict) else {}
    res = record.get("result") if isinstance(record.get("result"), dict) else {}
    data = record.get("data") if isinstance(record.get("data"), dict) else {}
    for c in (meta.get("url"), record.get("video_url"), record.get("url"), record.get("output_url"),
              res.get("video_url"), res.get("url"), data.get("video_url"), data.get("url")):
        if isinstance(c, str) and re.match(r"^https?://", c):
            return c
    return None


def _extract_ids(record):
    data = record.get("data") if isinstance(record.get("data"), dict) else {}
    rid = record.get("id") if isinstance(record.get("id"), str) else None
    video_id = record.get("video_id") or data.get("video_id") or (rid if rid and rid.startswith("video_") else None)
    task_id = record.get("task_id") or data.get("task_id") or rid
    return video_id, task_id


def _video_status_url(vid):
    if vid.startswith("task_"):
        return f"{VIDEO_CREATE}/{urllib.parse.quote(vid)}"
    return f"{VIDEO_POLL}?{urllib.parse.urlencode({'video_id': vid})}"


def _fetch_video_status(vid):
    """One status check. Returns a normalized dict."""
    status, body, elapsed = _request("GET", _video_status_url(vid), None, 60)
    if status == 503:
        return {"id": vid, "status": "queued", "note": "service busy", "elapsed": elapsed}
    if status == 404:
        return {"id": vid, "status": "failed", "error": "task not found", "elapsed": elapsed}
    if not 200 <= status < 300 or not isinstance(body, dict):
        raise AgnesError(f"Video status HTTP {status}: {_fmt_body(body)}")
    record = body
    return {
        "id": vid,
        "status": _normalize_status(record),
        "progress": record.get("progress"),
        "video_url": _extract_video_url(record),
        "seconds": record.get("seconds"),
        "size": record.get("size"),
        "error": record.get("error") or record.get("message") if _normalize_status(record) == "failed" else None,
        "elapsed": elapsed,
        "raw": record,
    }


async def _poll_video(vid, max_wait=600, interval=10):
    start = time.time()
    errors = 0
    while True:
        try:
            st = await asyncio.to_thread(_fetch_video_status, vid)
            errors = 0
        except AgnesError as e:
            errors += 1
            if errors >= 5:
                return {"id": vid, "status": "error", "error": str(e)}
            st = {"status": "queued"}
        if st["status"] == "completed" and st.get("video_url"):
            st["total_elapsed"] = round(time.time() - start, 1)
            return st
        if st["status"] in ("failed", "canceled"):
            return st
        if time.time() - start > max_wait:
            return {"id": vid, "status": "timed_out", "progress": st.get("progress")}
        await asyncio.sleep(interval)


def _download(url, prefix, ext):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    path = os.path.join(OUTPUT_DIR, f"{prefix}_{int(time.time())}{ext}")
    req = urllib.request.Request(url, headers={"User-Agent": "agnes-mcp/1.1"})
    with urllib.request.urlopen(req, timeout=300) as resp, open(path, "wb") as f:
        while True:
            chunk = resp.read(1 << 16)
            if not chunk:
                break
            f.write(chunk)
    return path


# ── Tool Definitions ─────────────────────────────────────────────────────────

TOOLS = [
    types.Tool(
        name="generate_image",
        description=(
            "Generate an image via Agnes Image API (agnes-image-2.1-flash by default). "
            "Modes: text2img (prompt only), img2img (1 reference image), compose (2+ images). "
            "Images may be URLs or local file paths (auto-uploaded). Non-English prompts are auto-translated. "
            "Returns image URL(s)."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "Image prompt (auto-translated if non-English)"},
                "mode": {"type": "string", "enum": ["text2img", "img2img", "compose"], "default": "text2img",
                         "description": "text2img, img2img (1 ref image), compose (2+ images)"},
                "images": {"type": "array", "items": {"type": "string"},
                           "description": "Image URLs, local file paths, or data URIs for img2img/compose"},
                "size": {"type": "string", "default": "1024x1024",
                         "description": "WIDTHxHEIGHT (e.g. 1024x1024, 1024x768), or 1K/2K combined with ratio"},
                "ratio": {"type": "string", "description": "Only used with size 1K/2K: 1:1, 16:9, 9:16, 4:3, 3:4, 3:2, 2:3"},
                "model": {"type": "string", "enum": IMAGE_MODELS, "description": "Override image model"},
                "seed": {"type": "integer"},
                "auto_translate": {"type": "boolean", "default": True},
                "ttl": {"type": "string", "enum": TTL_CHOICES, "default": "1h",
                        "description": "Lifetime of temporary uploads for local images"},
            },
            "required": ["prompt"],
        },
    ),
    types.Tool(
        name="generate_video",
        description=(
            "Create a video via Agnes Video API (agnes-video-v2.0). Modes: text2video, img2video (1 image), "
            "multivideo (2+ guiding images), keyframes (2+ keyframes). Images may be URLs or local paths. "
            "Video is async: returns a video id unless auto_poll is true. num_frames must be 8n+1 and <= 441."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "Video prompt (auto-translated if non-English)"},
                "mode": {"type": "string", "enum": ["text2video", "img2video", "multivideo", "keyframes"],
                         "default": "text2video"},
                "images": {"type": "array", "items": {"type": "string"},
                           "description": "Image URLs or local paths: 1 for img2video, 2+ for multivideo/keyframes"},
                "width": {"type": "integer", "default": 1152},
                "height": {"type": "integer", "default": 768},
                "num_frames": {"type": "integer", "default": 121, "description": "8n+1, max 441. 121 = 5s at 24fps"},
                "frame_rate": {"type": "integer", "default": 24, "description": "1-60"},
                "negative_prompt": {"type": "string"},
                "seed": {"type": "integer"},
                "auto_translate": {"type": "boolean", "default": True},
                "auto_poll": {"type": "boolean", "default": False, "description": "Wait for completion"},
                "max_wait": {"type": "integer", "default": 600, "description": "Seconds to wait when auto_poll"},
                "download": {"type": "boolean", "default": False, "description": "Download mp4 when completed"},
                "ttl": {"type": "string", "enum": TTL_CHOICES, "default": "1h"},
            },
            "required": ["prompt"],
        },
    ),
    types.Tool(
        name="get_video_result",
        description="Check an async Agnes video task (video_xxx or task_xxx id). Returns the video URL when completed.",
        input_schema={
            "type": "object",
            "properties": {
                "video_id": {"type": "string", "description": "video_id (preferred) or task_id from generate_video"},
                "wait": {"type": "boolean", "default": False, "description": "Keep polling until done"},
                "max_wait": {"type": "integer", "default": 600},
                "download": {"type": "boolean", "default": False},
            },
            "required": ["video_id"],
        },
    ),
    types.Tool(
        name="translate_prompt",
        description="Translate a non-English prompt to English using the Agnes text model.",
        input_schema={
            "type": "object",
            "properties": {"prompt": {"type": "string"}},
            "required": ["prompt"],
        },
    ),
    types.Tool(
        name="upload_media",
        description="Upload a local file to a temporary public host (Litterbox, fallback tmpfiles) and return its URL.",
        input_schema={
            "type": "object",
            "properties": {"file_path": {"type": "string"},
                           "ttl": {"type": "string", "enum": TTL_CHOICES, "default": "1h"}},
            "required": ["file_path"],
        },
    ),
]


# ── Tool implementations ─────────────────────────────────────────────────────

async def _do_generate_image(args):
    prompt = (args.get("prompt") or "").strip()
    if not prompt:
        raise AgnesError("prompt is required")
    mode = args.get("mode") or "text2img"
    images = [i for i in (args.get("images") or []) if i]
    model = args.get("model") or IMAGE_MODEL
    ttl = args.get("ttl") or "1h"

    if mode == "text2img" and images:
        mode = "img2img" if len(images) == 1 else "compose"
    if mode == "img2img" and len(images) != 1:
        raise AgnesError(f"img2img needs exactly 1 image, got {len(images)}")
    if mode == "compose" and len(images) < 2:
        raise AgnesError(f"compose needs at least 2 images, got {len(images)}")

    size = _normalize_size(args.get("size") or "1024x1024", args.get("ratio"))
    if args.get("auto_translate", True):
        prompt = await _translate_prompt(prompt)

    payload = {"model": model, "prompt": prompt}
    if size:
        payload["size"] = size
    if args.get("seed") is not None:
        payload["seed"] = int(args["seed"])
    if mode in ("img2img", "compose"):
        payload["extra_body"] = {"image": await _resolve_images(images, ttl), "response_format": "url"}

    result, elapsed = await asyncio.to_thread(_post_json, IMAGE_ENDPOINT, payload, 360)
    outputs = _extract_images(result)
    if not outputs:
        raise AgnesError(f"No image in response:\n{_fmt_body(result)}")
    return (f"[OK] {mode} in {elapsed:.1f}s\nModel: {model}\nSize: {size or 'default'}\n"
            f"Prompt: {prompt}\nImage(s):\n" + "\n".join(outputs))


async def _do_generate_video(args):
    prompt = (args.get("prompt") or "").strip()
    if not prompt:
        raise AgnesError("prompt is required")
    mode = args.get("mode") or "text2video"
    images = [i for i in (args.get("images") or []) if i]
    width = int(args.get("width") or 1152)
    height = int(args.get("height") or 768)
    num_frames = int(args.get("num_frames") or 121)
    frame_rate = int(args.get("frame_rate") or 24)
    ttl = args.get("ttl") or "1h"

    if mode == "text2video" and images:
        mode = "img2video" if len(images) == 1 else "keyframes"
    if num_frames > 441 or (num_frames - 1) % 8 != 0 or num_frames < 9:
        raise AgnesError(f"num_frames must be 8n+1 and between 9 and 441 (e.g. 81, 121, 241), got {num_frames}")
    if not 1 <= frame_rate <= 60:
        raise AgnesError(f"frame_rate must be 1-60, got {frame_rate}")
    if mode == "img2video" and len(images) != 1:
        raise AgnesError(f"img2video needs exactly 1 image, got {len(images)}")
    if mode in ("multivideo", "keyframes") and len(images) < 2:
        raise AgnesError(f"{mode} needs at least 2 images, got {len(images)}")

    if args.get("auto_translate", True):
        prompt = await _translate_prompt(prompt)

    payload = {"model": VIDEO_MODEL, "prompt": prompt, "width": width, "height": height,
               "num_frames": num_frames, "frame_rate": frame_rate}
    if args.get("seed") is not None:
        payload["seed"] = int(args["seed"])
    if args.get("negative_prompt"):
        payload["negative_prompt"] = args["negative_prompt"]
    if mode == "img2video":
        payload["image"] = (await _resolve_images(images, ttl))[0]
    elif mode == "multivideo":
        payload["extra_body"] = {"image": await _resolve_images(images, ttl)}
    elif mode == "keyframes":
        payload["extra_body"] = {"image": await _resolve_images(images, ttl), "mode": "keyframes"}

    result, elapsed = await asyncio.to_thread(_post_json, VIDEO_CREATE, payload, 120)
    video_id, task_id = _extract_ids(result)
    poll_id = video_id or task_id
    if not poll_id:
        raise AgnesError(f"No video_id/task_id in response:\n{_fmt_body(result)}")

    header = (f"Mode: {mode}\nModel: {VIDEO_MODEL}\nVideo ID: {video_id or '-'}\nTask ID: {task_id or '-'}\n"
              f"Prompt: {prompt}")
    if args.get("auto_poll"):
        st = await _poll_video(poll_id, max_wait=int(args.get("max_wait") or 600))
        return _format_video_status(st, header, bool(args.get("download")))
    return (f"[OK] Task created in {elapsed:.1f}s\n{header}\nStatus: {result.get('status', 'queued')}\n"
            f"Next: call get_video_result with video_id='{poll_id}'")


def _format_video_status(st, header="", download=False):
    prefix = (header + "\n") if header else ""
    s = st.get("status")
    if s == "completed" and st.get("video_url"):
        lines = [f"[COMPLETED] Video ready", prefix.rstrip(), f"Video URL: {st['video_url']}"]
        if st.get("seconds"):
            lines.append(f"Duration: {st['seconds']}s")
        if st.get("size"):
            lines.append(f"Size: {st['size']}")
        if download:
            try:
                lines.append(f"Saved to: {_download(st['video_url'], 'agnes_video', '.mp4')}")
            except Exception as e:
                lines.append(f"Download failed: {e}")
        return "\n".join(l for l in lines if l)
    if s in ("failed", "canceled", "error"):
        raise AgnesError(f"Video {s}: {st.get('error') or 'unknown error'}\n{prefix}")
    if s == "timed_out":
        return f"[TIMEOUT] Still running.\n{prefix}Call get_video_result with video_id='{st.get('id')}' later."
    prog = st.get("progress")
    return (f"[{str(s).upper()}] Progress: {prog if prog is not None else '?'}%\n{prefix}"
            f"Call get_video_result again with video_id='{st.get('id')}'.")


async def _do_get_video_result(args):
    vid = (args.get("video_id") or "").strip()
    if not vid:
        raise AgnesError("video_id required")
    if args.get("wait"):
        st = await _poll_video(vid, max_wait=int(args.get("max_wait") or 600))
    else:
        st = await asyncio.to_thread(_fetch_video_status, vid)
    return _format_video_status(st, f"Video ID: {vid}", bool(args.get("download")))


async def _do_translate(args):
    prompt = args.get("prompt", "")
    if not _needs_translation(prompt):
        return f"[INFO] Prompt is already English, no translation needed.\n{prompt}"
    translated = await _translate_prompt(prompt)
    if translated == prompt:
        raise AgnesError("Translation failed (check AGNES_API_KEY and network).")
    return f"[OK] Translated:\n{translated}"


async def _do_upload(args):
    file_path = os.path.expanduser(args.get("file_path", ""))
    ttl = args.get("ttl", "1h")
    if not os.path.isfile(file_path):
        raise AgnesError(f"File not found: {file_path}")
    url = await asyncio.to_thread(_upload_media, file_path, ttl)
    return f"[OK] Uploaded (TTL: {ttl})\nURL: {url}"


HANDLERS = {
    "generate_image": _do_generate_image,
    "generate_video": _do_generate_video,
    "get_video_result": _do_get_video_result,
    "translate_prompt": _do_translate,
    "upload_media": _do_upload,
}


# ── MCP handlers (MCP Python SDK 2.x: handler(ctx, params)) ──────────────────

def _text_result(text, is_error=False):
    return types.CallToolResult(content=[types.TextContent(type="text", text=text)], is_error=is_error)


async def _handle_list_tools(ctx, params=None) -> types.ListToolsResult:
    return types.ListToolsResult(tools=TOOLS)


async def _handle_call_tool(ctx, params: types.CallToolRequestParams) -> types.CallToolResult:
    handler = HANDLERS.get(params.name)
    if not handler:
        return _text_result(f"[ERROR] Unknown tool: {params.name}", True)
    try:
        if params.name != "upload_media":
            _get_key()
        return _text_result(await handler(params.arguments or {}))
    except AgnesError as e:
        return _text_result(f"[ERROR] {_redact(str(e))}", True)
    except Exception as e:
        return _text_result(f"[ERROR] {type(e).__name__}: {_redact(str(e))}", True)


server = Server("agnes-mcp", on_list_tools=_handle_list_tools, on_call_tool=_handle_call_tool)


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
