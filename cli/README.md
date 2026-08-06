# Agnes-AI

![Agnes-AI](https://github.com/user-attachments/assets/4cbcaa09-e704-4c9b-90ba-b89b1b7fbc90)
A unified Python CLI for Agnes AI models — text generation, image
understanding, image generation, and video generation, all with zero external
dependencies.

Built by [AI Lab](https://github.com/1038lab). This repo wraps every Agnes API
endpoint into a single `agnes.py` with sensible defaults, auto-translation,
and dry-run validation — no pip install required.

**What's inside:**

```
scripts/agnes.py   →  CLI (text, image understanding, image, video)
SKILL.md           →  Agent skill for AI coding assistants
examples/server.py →  Web playground at http://localhost:8888
```

**Why use this?**

- **Zero dependencies** — Python stdlib only, works out of the box
- **Agent-ready** — ships with SKILL.md and playground for testing
- **Auto-translate** — write prompts in any language
- **Dry-run mode** — validate before spending credits
- **Smart defaults** — sizes, frame counts, polling — all pre-configured
- **Free to use** — no GPU needed, just an API key

## Overview

- **Text generation** — chat, tool calling, streaming
- **Image understanding** — describe images with agnes-2.0-flash multimodal
- **Image generation** — text2img, img2img, multi-image compose
- **Video generation** — text2video, img2video, keyframe animation
- **Auto-translate** — non-English prompts translated to English automatically
- **Zero dependencies** — Python stdlib only, no pip install required

## Installation

Requires Python 3.8+ and an Agnes AI API key.

```bash
# Clone the repository
git clone https://github.com/1038lab/Agnes-AI.git
cd Agnes-AI

# Optionally add scripts to your PATH
export PATH="$PWD/scripts:$PATH"
```

## Getting an API Key

1. Sign up at [https://apihub.agnes-ai.com](https://apihub.agnes-ai.com)
2. Go to **API Keys** in your dashboard
3. Click **Create API Key** and copy the `sk-...` key

## Quick Start

```bash
# Set your API key
export AGNES_API_KEY="your-key-here"

# Or use the interactive setup
python scripts/agnes.py setup

# Generate text
python scripts/agnes.py text --prompt "Hello, introduce yourself"

# Describe an image
python scripts/agnes.py text --prompt "Describe this image in detail" --image-url photo.jpg

# Generate an image
python scripts/agnes.py image text2img --prompt "A cat wearing a spacesuit, digital art"

# Generate a video
python scripts/agnes.py video text2video --prompt "Ocean waves at sunset, cinematic quality"
```

## CLI Reference

### Global Options

| Option | Description |
|--------|-------------|
| `--dry-run` | Print request body without calling the API |
| `--no-translate` | Disable automatic prompt translation |
| `--verbose` | Print debug info to stderr |

### `agnes setup`

Save your API key to your shell profile (`~/.zshrc` / `~/.bashrc` / `~/.profile`).

```bash
agnes setup
```

### `agnes text`

Text generation, chat completions, and image understanding (multimodal).

```bash
agnes text --prompt "Write a poem about artificial intelligence"
agnes text --prompt "Describe this image in detail" --image-url photo.jpg
agnes text --system "Analyze the art style" --image-url painting.png
agnes text --prompt "Write a sorting algorithm in Python" --system "You are a senior engineer"
agnes text --prompt "Tell me a joke" --stream
agnes text --prompt "History of computing" --temperature 0.9 --max-tokens 2048
agnes text --prompt "What is 1+1?" --message "user: What is 2+2?" --message "assistant: 4"
```

| Argument | Description |
|----------|-------------|
| `--prompt` | Prompt text (optional with `--image-url`) |
| `--image-url` | Image file path or URL for multimodal understanding |
| `--system` | System prompt |
| `--message` | Multi-turn messages (repeatable, format `role: content`) |
| `--stream` | Enable streaming output |
| `--temperature` | Sampling temperature (default 0.7) |
| `--top-p` | Top-p sampling (default 0.9) |
| `--max-tokens` | Max output tokens (default 4096) |
| `--tools-json` | Tool definitions as JSON |
| `--tool-choice` | Tool selection strategy |
| `--json-output` | Output as JSON |

### `agnes image`

Image generation.

![Agnes-AI Image](https://github.com/user-attachments/assets/dd371b71-e93a-4fb4-b98a-ad6ef4ffc78c)

```bash
# Text-to-image
agnes image text2img --prompt "Cyberpunk city at night"

# Image-to-image
agnes image img2img --prompt "Make it look like a watercolor" --image-url https://example.com/photo.jpg

# Compose multiple images
agnes image compose --prompt "Blend these images" \
  --image-url https://example.com/img1.jpg \
  --image-url https://example.com/img2.jpg

# Custom size and download directory
agnes image text2img --prompt "An oil painting" --size "1920x1080" --output-dir ./output
```

| Argument | Description |
|----------|-------------|
| `mode` | Mode: `text2img` / `img2img` / `compose` (required) |
| `--prompt` | Prompt text (required) |
| `--image-url` | Reference image URL(s), repeatable |
| `--size` | Image dimensions (default `1024x768`) |
| `--output-dir` | Download directory (omit to print URLs only) |

### `agnes video`

Video generation with automatic polling and optional download.

![Agnes-AI Video](https://github.com/user-attachments/assets/6ea1e190-412a-4950-913b-9f30d8aa7d1e)

```bash
# Text-to-video (auto-poll)
agnes video text2video --prompt "A butterfly flying through a flower field"

# Image-to-video
agnes video img2video --prompt "Animate this image" --image-url https://example.com/photo.jpg

# Keyframe video (start and end frames)
agnes video keyframes --prompt "Animation sequence" \
  --image-url https://example.com/frame1.jpg \
  --image-url https://example.com/frame2.jpg

# Custom parameters
agnes video text2video --prompt "Waterfall" \
  --width 1920 --height 1080 \
  --num-frames 241 --frame-rate 30 \
  --seed 42 --negative-prompt "blurry, noisy" \
  --download --output-dir ./videos

# Disable polling, just get the task_id
agnes video text2video --prompt "Sunset" --no-poll
```
https://github.com/user-attachments/assets/25af3d70-c242-4c10-9320-6107f23b9320

| Argument | Description |
|----------|-------------|
| `mode` | Mode: `text2video` / `img2video` / `keyframes` (required) |
| `--prompt` | Prompt text (required) |
| `--image-url` | Reference image URL(s), repeatable |
| `--width` | Video width (default 1152) |
| `--height` | Video height (default 768) |
| `--num-frames` | Number of frames (default 121, must satisfy 8n+1, max 441) |
| `--frame-rate` | Frames per second (default 24, range 1–60) |
| `--seed` | Random seed for reproducibility |
| `--num-inference-steps` | Number of denoising steps |
| `--negative-prompt` | Things to avoid in the video |
| `--no-poll` | Disable automatic polling |
| `--poll-interval` | Poll interval in seconds (default 10) |
| `--timeout` | Timeout in seconds (default 900) |
| `--download` | Download video after completion |
| `--output-dir` | Output directory |

### `agnes poll`

Poll for video generation status.

```bash
agnes poll VIDEO_ID
agnes poll VIDEO_ID --poll-interval 5 --timeout 600
agnes poll VIDEO_ID --download --output-dir ./videos
```

### `agnes smoke-test`

Run end-to-end smoke tests in dry-run mode (no API calls).

```bash
agnes smoke-test
agnes smoke-test --video-case text2video
```

## Features

### Auto-Translation

When a prompt contains non-ASCII characters, `agnes` automatically translates it to English using `agnes-2.0-flash` before sending it to the target model. Use `--no-translate` to disable.

```bash
# Auto-translate (default)
agnes image text2img --prompt "一只橘猫在窗台上晒太阳"

# Equivalent to manually translating then:
agnes image text2img --prompt "An orange cat basking in the sun on a windowsill" --no-translate
```

### Automatic Media Upload

For `img2img`, `compose`, `img2video`, and `keyframes` modes, you can pass local file paths to `--image-url`. The tool will automatically upload the file to Litterbox and use the public URL.

```bash
agnes image img2img --prompt "Make it cartoon style" --image-url ./my-photo.jpg
agnes video keyframes --prompt "Scene transition" --image-url ./start.png --image-url ./end.png
```

### Video Auto-Polling

Video generation polls for completion by default. Pass `--download` to save the result locally.

### Dry-Run Mode

Use `--dry-run` to inspect the request payload without calling the API:

```bash
agnes image text2img --prompt "test" --dry-run
agnes video text2video --prompt "test" --dry-run
```

## Usage Limits

| Plan | Price | Limits |
|------|-------|--------|
| Free Access | $0 | Fair-use quota (no hard cap), basic TPS limit |
| Starter | $2/mo | 1500 requests per 5 hours, higher RPM |
| Plus | $5/mo | 7500 requests per 5 hours, higher RPM |
| Pro | $25/mo | 30000 requests per 5 hours, higher RPM |

See [Common Error Codes](references/errors.md) for API error descriptions.

## Changelog

| Date | Changes |
|------|---------|
| 2026-07-09 | Added image understanding (multimodal describe); new Describe Image sub-mode in Playground Text tab; CLI preview placeholders use `{image}` (avoids innerHTML tag-eating); fixed centered text in result area; README rewrite, renamed to Agnes-AI, detailed API key guide, AILab credit |
| 2026-07 | Fixed Image API format: img2img/compose `image` field moved to top level (not inside `extra_body`); Playground size selection redesigned with ratio/resolution/duration (Pavo AI style); Playground result area fixed (max-width, height auto, no flex); Image timeout 120s → 300s; `text.py` `resp.read()` moved inside try block |

## Zero-Dependency Philosophy

The entire project uses only Python standard library modules — no pip install required:

- `urllib.request` — HTTP requests
- `argparse` — CLI argument parsing
- `json` — serialization
- `os`, `sys`, `time`, `mimetypes` — system utilities
- `re` — string processing (setup command)

## Interactive Playground

A web UI for all features — no terminal needed:

```bash
# One-click launch
open examples/start.command

# Or manually
python3 examples/server.py
```

Open http://localhost:8888 to use:
- **Text** — chat / streaming / JSON output / image description
- **Image** — text2img / img2img / compose, all sizes with ratio labels
- **Video** — text2video / img2video / start & end frames, with FPS and duration preview

## Project Structure

```
Agnes-AI/
├── scripts/          # Core Python modules
│   ├── agnes.py      # CLI entry point and dispatch
│   ├── text.py       # Text generation
│   ├── image.py      # Image generation
│   ├── video.py      # Video generation + polling
│   ├── translate.py  # Auto-translation
│   └── media.py      # Media upload and download
├── references/       # API reference + error codes
├── examples/         # Playground web UI + server
├── tests/            # Smoke tests (no framework needed)
└── agents/           # Agent configuration files
```

## Environment Variables

| Variable | Description |
|----------|-------------|
| `AGNES_API_KEY` | Primary API key |
| `AGNES_API_TOKEN` | Fallback API key |
| `APIHUB_AGNES_API_KEY` | Fallback API key |
| `AGNES_API_BASE` | API base URL (default `https://apihub.agnes-ai.com`) |

## License

GNU General Public License v3.0. See [LICENSE](LICENSE).

## Links

- [API Reference](references/api.md)
- [Error Codes](references/errors.md)
- [Agnes AI](https://agnes-ai.com)
- [API Hub](https://apihub.agnes-ai.com)
- [ComfyUI-Agnes-AI](https://github.com/1038lab/ComfyUI-Agnes-AI) — ComfyUI custom nodes built on this toolkit
