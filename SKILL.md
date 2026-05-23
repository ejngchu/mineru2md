---
name: mineru2md
description: >
  Parse images, PDFs, Office files (Word, PowerPoint, Excel), HTML pages, and article URLs into Markdown
  via MinerU APIs. Automatically routes between Lightweight API (free, no token, ≤10MB/≤20 pages) and
  Precision API (token required, larger files).
  Activates when user sends an image/screenshot, provides a file path, pastes a URL, or asks to
  "extract text", "convert to markdown", "parse this image/file".
license: MIT
compatibility: Requires Python 3.8+ and `requests` library. PyMuPDF optional for page count detection.
token_required: false  # Only for files >10MB or >20 pages
metadata:
  author: mineru2md
  version: "2.0"
  triggers:
    - "提取文字"
    - "转换 markdown"
    - "解析图片"
    - "解析文件"
    - "convert to markdown"
    - "extract text from"
    - "parse this image"
    - "parse this file"
    - "parse this screenshot"
---

# MinerU2MD Skill

Convert images, PDFs, Office documents, and URLs to Markdown using [MinerU](https://mineru.net) APIs.

## When This Skill Activates

This skill activates when the user:
- Sends an image or screenshot
- Provides a file path (`.pdf`, `.png`, `.jpg`, `.docx`, `.pptx`, `.xlsx`, etc.)
- Pastes a URL for content extraction
- Says: "提取文字", "转换 markdown", "解析图片/文件", "convert to markdown", "extract text", "parse this"

## Intent Mapping

| User says | Action |
|-----------|--------|
| 发送图片/截图 | `python scripts/mineru2md.py --file {path} --print` |
| 发送 PDF 文件路径 | `python scripts/mineru2md.py --file {path} --print` |
| 发送 URL (文章) | `python scripts/mineru2md.py --url {url} --print` |
| 发送文件列表 | `python scripts/mineru2md.py --files {paths} --output {dir}/` |
| "提取文字" + 图片 | 识别图片路径，调用 Lightweight API |
| "转换 markdown" + 文件 | 识别文件路径，自动选择 API |
| 请求查看 token 状态 | 检查 `assets/config.json` 是否存在有效 token |

## Auto-Routing Logic

```
File conditions → Lightweight API (free, no token)
  ✓ ≤10MB AND ≤20 pages AND supported type (PDF, images, DOCX, PPTX, XLSX)

File conditions → Precision API (token required)
  ✗ >10MB OR >20 pages OR HTML file OR direct file URL
```

**Article URLs** (no file extension): tries Lightweight first → falls back to Precision if fails.
**File URLs** (`.pdf`, `.doc`, etc.): Precision API only.

## Supported Formats

| Type | Extensions | Lightweight | Precision |
|------|-----------|:----------:|:---------:|
| Images | PNG, JPG, WebP, BMP, GIF, JP2 | ≤10MB | ✓ |
| PDF | PDF | ≤20 pages | ✓ |
| Word | DOCX | ≤20 pages | ✓ |
| PowerPoint | PPTX | ≤20 pages | ✓ |
| Excel | XLSX | ≤20 pages | ✓ |
| HTML | HTML, HTM | ✗ | ✓ |

## Token Management

**Token storage**: `assets/config.json` — persists across sessions.

**When token is needed**:
- File > 10MB
- File > 20 pages
- File is HTML
- Direct file URL (not article URL)

**If no token but required**:
```
Ask user: "需要 MinerU Token 来处理大文件。请从 https://mineru.net 获取 token。"
```

**Get token**:
```bash
# Linux/macOS/Git Bash
export MINERU_TOKEN='your_token'

# Windows PowerShell
$env:MINERU_TOKEN='your_token'
```

## Core Commands

```bash
# Single file — auto-select API
python scripts/mineru2md.py --file ./doc.pdf --print

# URL (article auto-routes)
python scripts/mineru2md.py --url https://example.com/article --print

# Batch files (Precision API)
python scripts/mineru2md.py --files f1.pdf f2.pdf --output ./results/

# With options
python scripts/mineru2md.py --file ./doc.pdf --enable-formula --enable-table --language en

# Page ranges
python scripts/mineru2md.py --file ./doc.pdf --page-ranges 1-10,15,20-25

# Print instead of save
python scripts/mineru2md.py --file ./doc.pdf --print
```

## Skill Structure

```
~/.config/opencode/skills/mineru2md/
├── SKILL.md              # This file
├── scripts/
│   └── mineru2md.py     # Main CLI
├── references/
│   └── python-api.md    # Python API docs
├── assets/
│   └── config.json      # Token storage
└── tests/
    ├── __init__.py
    └── test_mineru2md.py # 39 unit tests
```

## Error Handling

| Code | Meaning | Action |
|------|---------|--------|
| A0202 | Token incorrect | Check token format in config.json |
| A0211 | Token expired | Get new token from MinerU dashboard |
| -60005 | File > 200MB | Split the file |
| -60006 | Page count > 200 | Split the PDF |
| -30001 | File > 10MB for Lightweight | Auto-fallback to Precision |

## Testing

```bash
cd ~/.config/opencode/skills/mineru2md
pytest tests/ -v  # 39 tests
```
