# Agnes MCP — Unified Agnes AI Image & Video Generation Toolkit

A unified toolkit for the [Agnes AI](https://agnes-ai.com) API, providing three access layers:

| Layer | Path | What it does | License |
|-------|------|-------------|---------|
| **MCP Server** | `mcp-server/` | 5 tools accessible from any MCP-compatible AI client (WorkBuddy, Claude Desktop, Cursor, VS Code) | MIT |
| **CLI** | `cli/` | Zero-dependency Python CLI — text/image/video generation from terminal | GPL v3 |
| **Skill** | `skill/` | WorkBuddy Skill with prompt library and showcase examples | MIT |

## MCP Server Tools

| Tool | Description |
|------|-------------|
| `generate_image` | Text-to-image, image-to-image, multi-image compose. Auto-translates non-English prompts. |
| `generate_video` | Text-to-video, image-to-video, multi-image video, keyframe animation. Auto-translate + optional auto-poll. |
| `get_video_result` | Poll for async video task result. |
| `translate_prompt` | Translate non-English prompt to English via agnes-2.0-flash. |
| `upload_media` | Upload local file to a temporary host (Litterbox, fallback tmpfiles), get public URL for img2img/img2video. |

## Quick Start

### MCP Server (WorkBuddy / Claude Desktop / Cursor)

Requires Python 3.10+ and MCP Python SDK 2.x:

```bash
pip install -r mcp-server/requirements.txt
```

Add the server to your MCP client config (this file lives on your machine, not in this repo):

```json
{
  "mcpServers": {
    "agnes-mcp": {
      "command": "python",
      "args": ["/absolute/path/to/agnes-mcp/mcp-server/agnes_mcp.py"],
      "env": { "AGNES_API_KEY": "your-key" }
    }
  }
}
```

### Keeping your API key private

Never put your key in code or commit it. Use one of these:

1. **MCP client config** — the `env` block above. That config file is local to your computer.
2. **Local `.env` file** — `cp .env.example .env`, then fill in `AGNES_API_KEY`. `.env` is in `.gitignore`, so `git` will not upload it. The server reads it automatically.
3. **Shell environment** — `export AGNES_API_KEY=...` in `~/.zshrc` / `~/.bashrc`.

Get a key at <https://platform.agnes-ai.com/settings/apiKeys>. If a key ever gets pushed to GitHub, revoke it there and create a new one.

### API notes

| Capability | Endpoint | Notes |
|---|---|---|
| Image | `POST https://apihub.agnes-ai.com/v1/images/generations` | `size` is `WIDTHxHEIGHT`; reference images go in `extra_body.image` as a URL array |
| Video create | `POST https://apihub.agnes-ai.com/v1/videos` | `num_frames` must be 8n+1 and ≤ 441; `frame_rate` 1–60 |
| Video status | `GET /agnesapi?video_id=video_…` or `GET /v1/videos/task_…` | Async; poll until `completed`/`succeeded` |

Local image paths are uploaded to a temporary public host (Litterbox, fallback tmpfiles) because Agnes needs public image URLs.

### CLI (terminal)

```bash
export AGNES_API_KEY=your-key
python cli/agnes.py image text2img --prompt "A sunset over Tokyo"
python cli/agnes.py video text2video --prompt "A cat walking on the beach"
```

### Skill (WorkBuddy)

Copy `skill/SKILL.md` to `~/.workbuddy/skills/agnes-image-gen/SKILL.md`.

## Features

- **Auto-translate**: Non-English prompts auto-translated via agnes-2.0-flash
- **Auto-upload**: Local images auto-uploaded to Litterbox for URL-based operations
- **Auto-poll**: Video generation can auto-wait for completion (up to 600s)
- **Keyframe animation**: Generate video transitions between 2+ keyframe images
- **Multi-image compose**: Blend multiple reference images into one
- **Cross-tool**: MCP protocol works with any compatible AI client
- **Zero-dependency CLI**: Pure Python stdlib, no pip install needed

## Attribution

This project merges code and ideas from three sources. See `NOTICES.md` for details.

## Related Projects

These projects solve different problems and are intentionally kept separate:

| Project | What it does | When to use |
|---------|-------------|-------------|
| [Fashion-AI](https://github.com/liangdabiao/Fashion-AI) | 爆款检索 → 风格分析 → AI 生图 全流水线 (Milvus + LLM + Image Gen) | 跨境电商铺货，批量出图 |
| [Open PicsetAI](https://github.com/ym1100/open-picsetai) | 全品电商图工作台 (风格复刻/精修/PSD导出) | 团队生产环境，需要 Web UI |
| [EC-Portrait-Studio](https://github.com/mkhsu2002/EC-Portrait-Studio) | 多角度模特图生成 (Gemini + Firebase) | 服装类目，需要模特图 |
| [Amazon Image Studio](https://github.com/Ali-Aria/amazon-image-studio) | Amazon Listing 图策划 + 生成 | 亚马逊卖家 |

## License

- `mcp-server/` — MIT
- `cli/` — GPL v3 (from 1038lab/Agnes-AI)
- `skill/` — MIT (from jomeswang/agnes-ai-skill)
- Root project — MIT
