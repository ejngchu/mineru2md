# MinerU2MD

Convert PDF, images, Word, PowerPoint, Excel files and URLs to Markdown using [MinerU](https://mineru.net) APIs.

Auto-routes between **Lightweight Agent API** (no token, ≤10MB, ≤20 pages) and **Precision API** (token required, larger or complex files).

## Requirements

- Python 3.8+
- `requests` library

```bash
pip install requests
```

Optional (for page count reading in Precision API routing):
```bash
pip install PyMuPDF
```

## Usage

```bash
python mineru2md.py -h
python mineru2md.py --help-languages   # List all supported language codes
```

### Quick Start — Single File

```bash
# Lightweight API (no token required) — auto-selected when file ≤10MB and ≤20 pages
python mineru2md.py --file ./small.pdf

# Force Precision API (token required) — even for small files
python mineru2md.py --file ./small.pdf --force-precision

# Precision API (token required) — auto-selected when file >10MB or >20 pages
python mineru2md.py --file ./large.pdf
```

### Single URL — Article URLs Auto-Routed (Lightweight First)

```bash
# Direct file URL (PDF, image, doc) → Precision API (token required)
export MINERU_TOKEN='your_token'
python mineru2md.py --url https://example.com/document.pdf

# Article URL (web page, WeChat, etc.) → tries Lightweight API first (no token),
# falls back to Precision API if needed
python mineru2md.py --url https://mp.weixin.qq.com/s/article
```

Article URLs (no file extension or `.html`/`.htm`) automatically:
1. Try **Lightweight API** first (no token needed)
2. If Lightweight fails → fallback to **Precision API** (token required)

### Batch Processing

```bash
# Multiple files — ALL files go through Precision API batch upload (token required)
# Token is auto-retrieved from MINERU_TOKEN env var if not provided
python mineru2md.py --files file1.pdf file2.pdf image.png --output-dir ./results

# Scan a directory for files to process
python mineru2md.py --files ./pdfs/*.pdf --output-dir ./results

# Multiple URLs (each processed individually — article URLs try Lightweight first)
python mineru2md.py --urls url1.pdf url2.pdf --output-dir ./results
```

> **Note**: `--files` mode always uses Precision API (batch upload in a single API call). For Lightweight API, use `--file` (single file only).

### Optional Parameters

```bash
# Enable formula / table recognition
python mineru2md.py --file ./doc.pdf --enable-formula --enable-table

# Disable formula / table recognition
python mineru2md.py --file ./doc.pdf --disable-formula --disable-table

# Enable OCR
python mineru2md.py --file ./doc.pdf --is-ocr

# Set document language (default: ch)
python mineru2md.py --file ./doc.pdf --language en

# Extract specific page ranges only (supports comma-separated ranges)
python mineru2md.py --file ./doc.pdf --page-ranges 1-10,15,20-25

# Request additional export formats
python mineru2md.py --file ./doc.pdf --extra-formats docx --extra-formats html

# Bypass cache
python mineru2md.py --url https://example.com/doc.pdf --no-cache

# Set cache tolerance (seconds)
python mineru2md.py --url https://example.com/doc.pdf --cache-tolerance 1800

# Longer polling timeout (default: 300s)
python mineru2md.py --file ./doc.pdf --timeout 600

# Print markdown to stdout instead of saving to file
python mineru2md.py --file ./doc.pdf --print

# Prepend current date (YYYY-MM-DD) to output filename
python mineru2md.py --file ./doc.pdf --timestamp

# Combine: print article URL result with timestamp-based filename
python mineru2md.py --url https://example.com/article --print --timestamp
```

## Token Setup

Precision API is needed when:
- File > 10 MB
- File has > 20 pages
- File type is not in the supported lightweight list
- Input is a direct file URL (PDF, image, doc, etc.)
- `--force-precision` flag is used

**Article URLs** (web pages, no file extension or `.html`/`.htm`) try **Lightweight API first** (no token). Only fall back to Precision API (token required) if Lightweight fails.

```bash
# Windows PowerShell
$env:MINERU_TOKEN='your_token'

# Linux / macOS
export MINERU_TOKEN='your_token'
```

**Obtain a token** from the [MinerU platform](https://mineru.net) — the token must include the `Bearer ` prefix automatically by the script.

## Output Behavior

| Mode | Output File Name | Notes |
|------|-----------------|-------|
| `--file ./report.pdf` | `report.md` (same directory) | Use `--output result.md` to specify path |
| `--file ./doc.pdf --output ./out/doc.md` | `./out/doc.md` | Directory auto-created |
| `--url https://example.com/file.pdf` | `file.md` | Direct file URL → filename from URL path |
| `--url https://example.com/article` | `文章标题.md` | Article URL → filename from document title |
| `--url https://example.com/page.html` | `页面标题.md` | `.html`/`.htm` → filename from document title |
| `--files ... --output-dir ./results` | `./results/name1.md`, `./results/name2.md` | One `.md` per input file |
| `--urls ... --output-dir ./results` | Same as above | Article URLs use title; file URLs use URL path |

**`--timestamp`**: Prepends `YYYY-MM-DD ` to output filename (e.g., `2026-05-14 report.md`). Not applied when `--output` is specified.

**`--print`**: Outputs markdown content to stdout instead of saving to a file.

**Image extraction**: When Precision API is used and the result ZIP contains an `images/` folder, images are extracted into `{output_dir}/images/` (or `./images/`). Image references in the generated markdown are rewritten to point to local paths.

## Architecture — How Auto-Routing Works

### Routing Decision

The decision is made by `get_routing_decision(file_path, force_precision)`:

```
                       ┌─ force_precision=True ──▶ Precision API
                       │
  get_routing_decision()── is_lightweight_compatible(file)?
                       │        │
                       │    ┌───┴───┐
                       │    │       │
                       │   Yes     No ──▶ Precision API (with reasons)
                       │    │
                       ▼    ▼
                  Lightweight API
```

`is_lightweight_compatible()` checks **all**:
1. File extension ∈ {pdf, png, jpg, jpeg, jp2, webp, gif, bmp, docx, pptx, xlsx}
2. File size ≤ 10 MB
3. Page count ≤ 20 (PDF only; requires PyMuPDF)

If any condition fails → Precision API.

### Processing Flow

All inputs go through `parse_with_auto_routing()`:

```
                     ┌──────────────┐
                     │  Input       │
                     │ (file or URL)│
                     └──────┬───────┘
                            │
                     parse_with_auto_routing()
                            │
              ┌─────────────┴─────────────┐
              │                           │
           is_url=True                 is_url=False
              │                           │
      ┌───────┴───────┐           get_routing_decision()
      │               │                   │
  has_file_ext?  article URL          ┌───┴───┐
  (pdf,png,...)   (no ext or       Lightweight Precision
      │           .html/.htm)        API       API
      │               │
      ▼               ▼
  Precision     Try Lightweight API
  API only       (no token needed)
                    │
              ┌─────┴─────┐
            Success      Failed
              │            │
              ▼            ▼
          Return       Fallback to
          result      Precision API
                        (token)
                          │
                          ▼
                      Return result
```

**File URL** (e.g., `https://example.com/report.pdf`) → Precision API only (token required).

**Article URL** (e.g., `https://mp.weixin.qq.com/s/article` or `.html`/`.htm`):
1. Try **Lightweight API** (no token)
2. If Lightweight fails → **Precision API** (token required)

**Model detection**: Article URLs use `MinerU-HTML` model; file URLs use `vlm` model.

**Title-based naming**: Article URLs use the document's first `#` heading as the output filename.

### What Happens Per API

**Lightweight API** (no token):
1. `POST /api/v1/agent/parse/file` or `/parse/url` → get `task_id`
2. `GET /api/v1/agent/parse/{task_id}` → poll until `state="done"`
3. Download markdown from `markdown_url` in response

**Precision API** (token required):
1. `POST /api/v4/file-urls/batch` or `/extract/task/batch` → get upload URL or `batch_id`
2. Upload file via `PUT` to signed URL
3. `GET /api/v4/extract-results/batch/{batch_id}` → poll until `state="done"`
4. Download result ZIP from `full_zip_url`
5. Extract `full.md` and `images/` folder, rewrite image paths

## Error Handling

| Error Code | Cause | Recommended Action |
|-----------|-------|-------------------|
| Token missing | `MINERU_TOKEN` not set | Set environment variable |
| A0202 | Token incorrect | Verify token format (should include `Bearer ` prefix) |
| A0211 | Token expired | Obtain new token from MinerU |
| -60005 | File > 200MB | Reduce file size or split |
| -60006 | Page count > 200 | Split PDF into smaller parts |
| -30001 | File > 10MB + routed to Lightweight | Precision API auto-selected fallback |
| Polling timeout | 300s exceeded | Use `--timeout 600` for larger files |

When a batch item fails, the others continue. A summary of successes and failures is printed at the end.

## Programmatic API

```python
from mineru2md import MinerUError

# Process a file with auto-routing
md_content, filename, output_dir = parse_with_auto_routing(
    "document.pdf",
    token="your_token",  # or None for lightweight-compatible files
    optional_params={"enable_formula": True, "language": "en"}
)

print(md_content[:500])  # First 500 chars of markdown

# Process a URL (always Precision API)
md_content, filename, _ = url_mode(
    "https://example.com/doc.pdf",
    token="your_token",
    optional_params={}
)

# Process via lightweight API directly (no token needed)
md_content, filename, _ = lightweight_file_mode(
    "small.pdf",
    optional_params={"enable_formula": True}
)
```

> **Note**: When using programmatically, catch `MinerUError` instead of relying on `sys.exit(1)` pattern. The CLI-only `sys.exit(1)` calls remain only in `main()`.

## File Types

| Format | Extensions | Lightweight API | Precision API |
|--------|-----------|:---:|:---:|
| PDF | `.pdf` | ✅ ≤20 pages, ≤10MB | ✅ |
| Images | `.png, .jpg, .jpeg, .jp2, .webp, .gif, .bmp` | ✅ ≤10MB | ✅ |
| Word | `.docx` | ✅ ≤10MB, ≤20 pages | ✅ |
| PowerPoint | `.pptx` | ✅ ≤10MB, ≤20 pages | ✅ |
| Excel | `.xlsx` | ✅ ≤10MB, ≤20 pages | ✅ |
| HTML | `.html, .htm` | ❌ | ✅ |

## OpenCode Skill Integration

This project can be used as an [OpenCode](https://github.com/call0n3/opencode) skill for seamless image-to-markdown conversion within the OpenCode assistant.

**Skill directory**: `~/.config/opencode/skills/mineru2md/`

**Structure**:
```
~/.config/opencode/skills/mineru2md/
├── SKILL.md          # Skill definition & user intent mapping
└── mineru2md.py      # Main script (symlinked or copied from repo)
```

**Loading the skill**: When you send an image or screenshot and want to extract content as markdown, OpenCode automatically loads the mineru2md skill and routes your request to the appropriate CLI command.

**Token persistence**: The skill saves your Precision API token to `~/.config/opencode/skills/mineru2md/config.json` so you only need to enter it once.

---

## License

MIT
