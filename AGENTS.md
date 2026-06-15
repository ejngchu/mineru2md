# AGENTS.md

## Project Structure

- Single-module package: `src/mineru2md/cli.py` (~1600 lines) is the entire library and CLI entry point.
- Entry: `mineru2md.cli:main` (registered in `setup.py` console_scripts).

## One-Liner Install (Skill + CLI)

```bash
git clone --depth=1 https://github.com/ejngchu/mineru2md /tmp/mineru2md_tmp && \
mkdir -p ~/.config/opencode/skills/mineru2md && \
cp -r /tmp/mineru2md_tmp/skill/* ~/.config/opencode/skills/mineru2md/ && \
cd /tmp/mineru2md_tmp && pip install -e . && \
rm -rf /tmp/mineru2md_tmp
```

This installs:
1. Skill metadata to `~/.config/opencode/skills/mineru2md/`
2. CLI tool `mineru2md` to PATH via `pip install -e .`

## Script Mode (No Install)

```bash
MINERU_TOKEN='your_token' python ./src/mineru2md/cli.py --file ./doc.pdf --print
```

## Architecture Facts an Agent Might Miss

- **URLs always route to Precision API** (token required). Lightweight `lightweight_parse_by_url()` exists but is never called from `parse_with_auto_routing()`.
- **Lightweight API** is free, needs no token, works only for local files ≤10MB + ≤20 pages + supported type (pdf/png/jpg/jpeg/jp2/webp/gif/bmp/docx/pptx/xlsx).
- **Precision API** required for: files >10MB, >20 pages, HTML, batch jobs, and ALL URLs.
- **PyMuPDF is optional** — only installed with `pip install -e .[pymupdf]`. Required for `get_page_count()`.
- **HTML is Precision-only** (not supported by Lightweight API at all).

## Testing

```bash
pytest tests/ -v                                     # all 45 tests
pytest tests/test_mineru2md.py::TestExtractFileExtension -v  # single class
```

- Tests import via `sys.path.insert("src")` — no package install needed.
- **`tests/samples/` is gitignored** — several tests are guarded by `if f.exists()` and will be silently skipped in a fresh checkout.
- Test classes are grouped by function name (`TestExtractFileExtension`, `TestGetFileSizeMb`, etc.), not plain functions.

## Token / Config

- Priority: `MINERU_TOKEN` env var > `~/.config/mineru2md/config.json`
- Config path is `~/.config/mineru2md/config.json` even on Windows (not `%APPDATA%`).
- Config auto-created on first run; `Bearer ` prefix added automatically.
- **`.env` file contains a real token** — never commit or expose it.

## Error Code Quick Reference

| Code | Meaning |
|------|---------|
| `A0202` | Token incorrect |
| `A0211` | Token expired |
| `-60005` | File >200MB |
| `-60006` | PDF >200 pages |
| `-30001` | File >10MB, auto-fallback to Precision |
