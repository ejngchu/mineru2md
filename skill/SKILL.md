---
name: mineru2md
description: >
  Parse images, PDFs, Office files, and URLs to Markdown via MinerU APIs.
  Activates when user sends an image, provides a file path, or pastes a URL.
  Auto-routes: Lightweight API (free, ≤10MB/≤20 pages) vs Precision API (token required).
triggers:
  - "提取文字" | "转换 markdown" | "解析图片/文件"
  - "convert to markdown" | "extract text" | "parse this image/file/screenshot"
token_required: false
license: MIT
---

## Intent → Action

| User input | Command |
|-----------|---------|
| Image / screenshot | `mineru2md --file {path} --print` |
| File path | `mineru2md --file {path} --print` |
| URL | `mineru2md --url {url} --print` |
| File list | `mineru2md --files {paths} --output {dir}/` |

## Token Setup

**Required for**: files >10MB, >20 pages, HTML, direct file URLs.

Token auto-created at `~/.config/mineru2md/config.json` (empty template on first run).

```bash
export MINERU_TOKEN='your_token'   # Linux/macOS/Git Bash
$env:MINERU_TOKEN='your_token'      # Windows PowerShell
```

**No token but needed**: ask user to get one from https://mineru.net and add to `~/.config/mineru2md/config.json`.

## Options

```bash
--print                  # stdout instead of file
--output <dir/>         # output directory
--enable-formula         # formula recognition
--enable-table           # table recognition
--language <lang>        # default: ch
--page-ranges <ranges>   # e.g. 1-10,15
--force-precision        # force Precision API
--timeout <seconds>      # default: 300
```

## Errors

| Code | Meaning |
|------|---------|
| A0202 | Token incorrect |
| A0211 | Token expired |
| -60005 | File > 200MB (split it) |
| -60006 | PDF > 200 pages (split it) |
| -30001 | File > 10MB, auto-fallback to Precision |
