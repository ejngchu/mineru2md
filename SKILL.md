---
name: mineru2md
description: Parse images, PDFs, Office files (Word, PowerPoint, Excel), HTML pages, and article URLs into Markdown via MinerU APIs. Use when the user sends an image or screenshot, provides a file path to a supported format, or asks to extract text/content from such files.
license: MIT
compatibility: Requires Python 3.8+ and `requests` library. Token needed for files ≥10MB or >20 pages.
metadata:
  author: mineru2md
  version: "2.0"
---

# mineru2md

Convert images, PDFs, Office documents, and article URLs to Markdown using [MinerU](https://mineru.net) APIs.

Auto-routes between **Lightweight API** (no token, ≤10MB, ≤20 pages) and **Precision API** (token required).

## When This Skill Activates

- User sends an image or screenshot
- User provides a file path (PDF, DOCX, PPTX, XLSX, images)
- User pastes a URL for extraction
- User says "extract text", "convert to markdown", "parse this"

## Quick Start

```bash
# Parse file (auto-routes Lightweight → Precision)
python scripts/mineru2md.py --file ./document.pdf --print

# Parse URL (article URLs auto-route)
python scripts/mineru2md.py --url https://example.com/article --print

# Batch files (Precision API)
python scripts/mineru2md.py --files file1.pdf file2.pdf --output ./results/
```

## How Auto-Routing Works

| File Condition | API Used | Token |
|----------------|----------|-------|
| ≤10MB, ≤20 pages, supported type | Lightweight | No |
| >10MB OR >20 pages | Precision | Yes |

**Article URLs** (no file extension, `.html`): tries Lightweight first → falls back to Precision if fails.

**Direct file URLs** (`.pdf`, `.doc`, etc.): Precision API only.

## Token Setup

Precision API requires token. Set via `MINERU_TOKEN` environment variable:

```bash
# Linux/macOS/Git Bash
export MINERU_TOKEN='your_token'

# Windows PowerShell
$env:MINERU_TOKEN='your_token'
```

Token is only needed when:
- File > 10MB
- File > 20 pages
- File is HTML
- Direct file URL

## Supported Formats

| Type | Extensions | Lightweight | Precision |
|------|-----------|:----------:|:---------:|
| Images | PNG, JPG, WebP, BMP, GIF | ≤10MB | ✓ |
| PDF | PDF | ≤20 pages | ✓ |
| Word | DOCX | ≤20 pages | ✓ |
| PowerPoint | PPTX | ≤20 pages | ✓ |
| Excel | XLSX | ≤20 pages | ✓ |
| HTML | HTML, HTM | ✗ | ✓ |

## Core Commands

```bash
# Single file (output to current directory)
python scripts/mineru2md.py --file ./doc.pdf

# Single file (output to directory)
python scripts/mineru2md.py --file ./doc.pdf --output ./output/

# Multiple files (output to directory)
python scripts/mineru2md.py --files f1.pdf f2.pdf --output ./results/

# Print to stdout
python scripts/mineru2md.py --file ./doc.pdf --print

# URL (article auto-routes)
python scripts/mineru2md.py --url https://example.com/article --output ./output/
```

## Skill Structure

```
~/.config/opencode/skills/mineru2md/
├── SKILL.md
├── scripts/
│   └── mineru2md.py
├── references/
│   └── python-api.md
├── assets/
│   └── config.json
└── samples/
```
