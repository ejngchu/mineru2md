---
name: mineru2md
description: Parse images, PDFs, Office files (Word, PowerPoint, Excel), HTML pages, and article URLs into Markdown via MinerU APIs. Use when the user sends an image or screenshot, provides a file path to a supported format, or asks to extract text/content from such files.
license: MIT
compatibility: Requires Python 3.8+ and `requests` library. Token needed for files ≥10MB or >20 pages.
metadata:
  author: mineru2md
  version: "1.0"
---

# mineru2md Image/File Parser

Convert images, PDFs, Office documents, and article URLs to Markdown using [MinerU](https://mineru.net) APIs. Auto-routes between **Lightweight Agent API** (no token, ≤10MB, ≤20 pages) and **Precision API** (token required).

## When This Skill Activates

Activate this skill when the user:
- Sends an image (PNG, JPG, JPEG, WebP, BMP, GIF) and wants text/markdown extracted
- Provides a PDF, DOCX, PPTX, XLSX, or HTML file path to convert
- Pastes a URL to a document/article for extraction
- Says "extract text", "convert to markdown", "parse this file", "OCR this image"

## Agent Workflow (step-by-step)

When activated, follow these steps **in order**:

### Step 1: Locate the file

The user may provide:
- An **absolute path** (e.g., `C:\Users\name\doc.pdf`)
- A **relative path** (resolve from current working directory)
- A **URL** (https://...)
- An **image attachment** (save to temp file first)

If the user pastes/clips an image directly, save it to a temporary file path first (e.g., using a temp directory).

### Step 2: Check file size and routing

The script auto-routes based on file characteristics:

| Condition | API Used | Token Required |
|-----------|----------|---------------|
| File ≤10MB AND ≤20 pages AND supported type | Lightweight API | No |
| File >10MB OR >20 pages OR unsupported type | Precision API | Yes |

For article URLs (no file extension, `.html`, `.htm`): tries Lightweight API first (no token), falls back to Precision API if it fails.

### Step 3: Get the token (if needed)

The Precision API token can come from **two places** (checked in order):

1. **`assets/config.json`** (project-level) — for local development
2. **`MINERU_TOKEN` environment variable** — for production/CI

If a token is needed but neither source provides one:
- Tell the user they need a MinerU Precision API token
- Ask them to provide it so you can save it to `assets/config.json`

**Important**: Load the token from `assets/config.json` using this structure:
```json
{
  "precision_token": "eyJ0eXBlIjoiSldUIi..."
}
```

### Step 4: Run the script

**Script location**: `scripts/mineru2md.py` (relative to skill root)

**Basic usage — parse & print to stdout:**
```bash
python scripts/mineru2md.py --file <path> --print
```

**With token (set env var before running):**
```bash
# Windows PowerShell
$env:MINERU_TOKEN='your_token'; python scripts/mineru2md.py --file <path> --print

# Linux/macOS/Git Bash
MINERU_TOKEN='your_token' python scripts/mineru2md.py --file <path> --print
```

**Save to directory:**
```bash
python scripts/mineru2md.py --file <path> --output-dir ./output
```

**Batch mode:**
```bash
python scripts/mineru2md.py --files file1.pdf file2.pdf --output-dir ./results
```

**URL mode (article auto-routing):**
```bash
# Article URL → tries Lightweight first, Precision fallback
python scripts/mineru2md.py --url https://example.com/article

# Direct file URL → Precision API only
python scripts/mineru2md.py --url https://example.com/doc.pdf
```

### Step 5: Return the result

- If `--print` was used: the markdown content is in stdout — return it to the user
- If `--output-dir` was used: the markdown file was saved to the output directory

## Supported Formats

| Type | Extensions | Lightweight (no token) | Precision (token) |
|------|-----------|:---------------------:|:-----------------:|
| Images | `.png`, `.jpg`, `.jpeg`, `.jp2`, `.webp`, `.gif`, `.bmp` | ≤10MB | Any size |
| PDF | `.pdf` | ≤10MB, ≤20 pages | Any |
| Word | `.docx` | ≤10MB, ≤20 pages | Any |
| PowerPoint | `.pptx` | ≤10MB, ≤20 pages | Any |
| Excel | `.xlsx` | ≤10MB, ≤20 pages | Any |
| HTML | `.html`, `.htm` | ❌ | Always |

## Skill Structure

```
~/.config/opencode/skills/mineru2md/
├── SKILL.md                  # Skill definition (this file)
├── scripts/
│   └── mineru2md.py          # Main executable
├── references/
│   └── python-api.md         # Python API reference
├── assets/
│   └── config.json           # Token config (gitignored)
└── samples/                  # Sample test files
```

## All CLI Commands

### Parse & Print
```bash
# Single file
python scripts/mineru2md.py --file image.png --print

# Batch
python scripts/mineru2md.py --files img1.png img2.jpg --print
```

### Save to Directory
```bash
python scripts/mineru2md.py --file image.png --output-dir ./output
python scripts/mineru2md.py --files img1.png img2.jpg --output-dir ./output
```

### With Optional Flags
```bash
python scripts/mineru2md.py --file doc.pdf --enable-formula --enable-table
python scripts/mineru2md.py --file doc.pdf --language en
python scripts/mineru2md.py --file doc.pdf --page-ranges 1-10,15,20-25
python scripts/mineru2md.py --file image.png --is-ocr
python scripts/mineru2md.py --file doc.pdf --force-precision
```

### Timestamp Filename
```bash
python scripts/mineru2md.py --file image.png --timestamp
python scripts/mineru2md.py --file image.png --output-dir ./output --timestamp
```

### URL Mode
```bash
# Direct file URL (token required)
python scripts/mineru2md.py --url https://example.com/doc.pdf

# Article URL (Lightweight first)
python scripts/mineru2md.py --url https://mp.weixin.qq.com/s/article

# Multiple URLs
python scripts/mineru2md.py --urls url1.pdf url2.pdf --output-dir ./results
```

### Batch Mode
```bash
python scripts/mineru2md.py --files file1.pdf file2.pdf --output-dir ./results
```

## Programmatic Python API

For using the skill via Python code (instead of CLI), see:

➡️ [Python API Reference](references/python-api.md)

Key entry points:
- `safe_parse_image(path, options)` — Parse single file with auto-routing
- `safe_parse_images(paths, options)` — Parse batch with auto-routing
- `parse_with_token(path, token, options)` — Parse with user-provided token

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `MINERU_TOKEN` | For ≥10MB or >20 pages | Precision API token (include `Bearer ` prefix) |

## Notes

- **Default behavior**: `--print` (stdout). Omit it to save to file.
- **Output filename**: Derived from input filename, or document title for article URLs.
- **Timestamp**: Use `--timestamp` to prepend date to output filename.
- **Token priority**: `assets/config.json` > `MINERU_TOKEN` env var > prompt user.
- **Image extraction**: Precision API results may include an `images/` subfolder.
- **Error handling**: If script fails, check the error output — common issues include token expiry, file not found, or unsupported format.
