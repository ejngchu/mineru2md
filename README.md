# MinerU2MD

Convert PDF, images, Word, PowerPoint, Excel files and URLs to Markdown using [MinerU](https://mineru.net) APIs.

## Features

- **Auto-routing**: Automatically selects the best API based on file characteristics
- **Lightweight Agent API**: Free, no token required (files ≤10MB, ≤20 pages)
- **Precision API**: For larger or complex files (token required)
- **Batch processing**: Convert multiple files or URLs at once
- **Image extraction**: Automatically extracts and rewrites image references
- **Rich optional parameters**: Formula recognition, table extraction, OCR, language selection, page ranges

## Installation

```bash
pip install requests
```

Or simply use it directly:
```bash
python mineru2md.py --file ./document.pdf
```

## Usage

### Single File

```bash
python mineru2md.py --file ./document.pdf
python mineru2md.py --file ./document.pdf --output result.md
```

### Single URL

```bash
python mineru2md.py --url https://example.com/document.pdf
```

### Batch Mode

```bash
python mineru2md.py --files file1.pdf file2.pdf --output-dir ./results
python mineru2md.py --urls url1.pdf url2.pdf --output-dir ./results
```

### Optional Parameters

```bash
# Enable formula and table recognition
python mineru2md.py --file ./doc.pdf --enable-formula --enable-table

# Specify document language
python mineru2md.py --file ./doc.pdf --language en

# Specify page ranges
python mineru2md.py --file ./doc.pdf --page-ranges 1-10,20

# Additional export formats
python mineru2md.py --file ./doc.pdf --extra-formats docx --extra-formats html

# Force Precision API (even for small files)
python mineru2md.py --file ./small.pdf --force-precision
```

### API Selection

| Mode | Condition | Token Required |
|------|-----------|----------------|
| Lightweight Agent API | ≤10MB, ≤20 pages, supported type | No |
| Precision API | >10MB OR >20 pages OR unsupported type OR URL | Yes |

### Environment Variables

```bash
# Windows
$env:MINERU_TOKEN='your_token'

# Linux/Mac
export MINERU_TOKEN='your_token'
```

## API Routing

The tool automatically routes requests:

**Lightweight Agent API** (no token needed):
- PDF, PNG, JPG, JPEG, JP2, WEBP, GIF, BMP, Docx, PPTx, Xlsx
- File size ≤ 10 MB
- Page count ≤ 20

**Precision API** (token required):
- Files exceeding Lightweight limits
- URLs
- All other file types

## Samples

Sample and demo PDF files can be downloaded from [MinerU API Documentation](https://mineru.net/apiManage/docs).

## License

MIT
