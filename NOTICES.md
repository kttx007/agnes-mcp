# Third-Party Notices

This project includes code and ideas from the following open-source projects:

## cli/ — Agnes-AI CLI

- **Source**: https://github.com/1038lab/Agnes-AI
- **Author**: 1038lab
- **License**: GNU General Public License v3 (GPL v3)
- **Files**: agnes.py, image.py, video.py, text.py, media.py, translate.py
- **Usage**: Included as-is for standalone CLI access

## skill/ — Agnes AI Skill

- **Source**: https://github.com/jomeswang/agnes-ai-skill
- **Author**: Jomes Wang
- **License**: MIT
- **Files**: SKILL.md, examples/
- **Usage**: Included as-is for WorkBuddy skill integration

## mcp-server/ — Enhanced MCP Server

- **Original**: kttx007/agnes-mcp (MIT)
- **Features ported from**: 1038lab/Agnes-AI (GPL v3)
  - Auto-translate (translate.py pattern)
  - Auto-upload / Litterbox (media.py pattern)
  - Auto-poll (video.py pattern)
  - Keyframe animation (video.py pattern)
  - Compose mode (image.py pattern)
- **Implementation**: Original async MCP code, not directly copied
- **License**: MIT
