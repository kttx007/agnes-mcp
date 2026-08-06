# References

This directory contains source code from related open-source projects, mirrored
for reference only. These projects solve different problems from agnes-mcp and
are NOT integrated into our codebase.

## Why mirrored?

We deliberately keep these as references rather than merging them into the main
codebase, because:
- Different tech stacks (Milvus / Next.js)
- Different users (production pipeline / web UI)
- Different problem domains (爆款检索 / Web editing)

## Sources

### fashion-ai/

- **Source**: https://github.com/liangdabiao/Fashion-AI
- **Stars**: 279
- **Purpose**: 电商 AI 生图爆款流水线 — 以图搜爆款 + 风格分析 + AI 生图
- **Tech**: Python, Milvus (vector DB), NVIDIA embedding API, Qwen LLM
- **License**: No LICENSE file in upstream repo — treated as source-available reference
- **Note**: Demonstrates full production pipeline (爆款检索 → 风格 prompt → AI 生图)

### open-picsetai/

- **Source**: https://github.com/ym1100/open-picsetai
- **Purpose**: 电商图片生成、精修与万能画布工作台
- **Tech**: Next.js 15, React 19, TypeScript, Tailwind, Canvas, PSD export
- **License**: MIT
- **Note**: Full-featured web application for e-commerce image editing

## Usage

These are reference materials. Read the source to learn patterns. To use them:

```bash
# Fashion-AI (爆款流水线)
cd references/fashion-ai
pip install -r requirements.txt
python main.py setup

# Open PicsetAI (Web 工作台)
cd references/open-picsetai
npm install
npm run dev
```

If you want to build on these patterns using Agnes API, the `mcp-server/` in the
parent directory provides a clean integration point.