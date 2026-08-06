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
| `generate_video` | Text-to-video, image-to-video, keyframe animation. Auto-translate + optional auto-poll. |
| `get_video_result` | Poll for async video task result. |
| `translate_prompt` | Translate non-English prompt to English via agnes-2.0-flash. |
| `upload_media` | Upload local file to Litterbox, get public URL for img2img/img2video. |

## Quick Start

### MCP Server (WorkBuddy / Claude Desktop / Cursor)

```json
{
  "mcpServers": {
    "agnes-mcp": {
      "command": "python",
      "args": ["mcp-server/agnes_mcp.py"],
      "env": { "AGNES_API_KEY": "your-key" }
    }
  }
}
```

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

## License

- `mcp-server/` — MIT
- `cli/` — GPL v3 (from 1038lab/Agnes-AI)
- `skill/` — MIT (from jomeswang/agnes-ai-skill)
- Root project — MIT
