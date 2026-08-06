# Agnes MCP Server

A [Model Context Protocol](https://modelcontextprotocol.io/) server that wraps the [Agnes AI](https://agnes-ai.com) Image & Video APIs.

## Tools

| Tool | Description |
|------|-------------|
| `generate_image` | Text-to-image / image-to-image (agnes-image-2.1-flash) |
| `generate_video` | Text-to-video / image-to-video (agnes-video-v2.0, async) |
| `get_video_result` | Poll for async video task result |

## Setup

### Prerequisites

- Python 3.10+
- `pip install mcp`

### Configuration

Set environment variables:

```bash
AGNES_API_KEY=your-api-key-here
AGNES_IMAGE_MODEL=agnes-image-2.1-flash  # optional
AGNES_VIDEO_MODEL=agnes-video-v2.0       # optional
```

### WorkBuddy

Add to `~/.workbuddy/mcp.json`:

```json
{
  "mcpServers": {
    "agnes-mcp": {
      "type": "stdio",
      "command": "python",
      "args": ["/path/to/agnes_image_video_mcp.py"],
      "env": {
        "AGNES_API_KEY": "your-key"
      }
    }
  }
}
```

### Claude Desktop

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "agnes-mcp": {
      "command": "python",
      "args": ["/path/to/agnes_image_video_mcp.py"],
      "env": {
        "AGNES_API_KEY": "your-key"
      }
    }
  }
}
```

### Cursor / VS Code

Same stdio config pattern — see your editor's MCP documentation.

## Usage

Once connected, any MCP-compatible AI client can call:

```
Generate an image of a sunset over Tokyo
Create a 5-second video of a cat walking on the beach
```

The AI will automatically use the appropriate tool.

## API Reference

- **Image API**: `POST https://apihub.agnes-ai.com/v1/images/generations`
- **Video API**: `POST https://apihub.agnes-ai.com/v1/videos` (async)
- **Video Poll**: `GET https://apihub.agnes-ai.com/agnesapi?video_id=<ID>`

## License

MIT
