# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

MinerU2MD converts PDF, images, Word, PowerPoint, Excel files and URLs to Markdown using [MinerU](https://mineru.net) APIs. Auto-routes between **Lightweight Agent API** (no token, ≤10MB, ≤20 pages) and **Precision API** (token required).

## Install

```bash
pip install -e .        # Editable install
pip install .           # Regular install
pip uninstall mineru2md # Uninstall
```

## Commands

```bash
mineru2md --file ./doc.pdf --print
mineru2md --url https://example.com/article --print
mineru2md --files f1.pdf f2.pdf --output ./results/
```

**Token**: Set via `MINERU_TOKEN` environment variable.

## API Routing

| File Condition | API | Token |
|----------------|-----|-------|
| ≤10MB, ≤20 pages, supported type | Lightweight | No |
| >10MB OR >20 pages | Precision | Yes |

## Key Files

- `mineru2md/api.py` — Main API and CLI (~1550 lines, well-sectioned)

## Testing

```bash
pytest tests/ -v           # All 39 tests
pytest tests/test_mineru2md.py::TestExtractFileExtension -v  # Single test class
```

## Architecture

The auto-routing decision flow is documented in `README.md` with diagrams. Key logic in `mineru2md/api.py`:

- `is_lightweight_compatible()` — checks file extension, size (≤10MB), and page count (≤20)
- `get_routing_decision()` — returns `'lightweight'` or `'precision'` with reason
- `parse_with_auto_routing()` — main entry point that routes based on decision
- `download_and_extract()` — handles Precision API ZIP output with image path rewriting

## Token Config

Token is loaded from (in priority order):
1. `MINERU_TOKEN` environment variable
2. `~/.config/mineru2md/config.json` (Linux/macOS)
3. `%APPDATA%/mineru2md/config.json` (Windows)

Config file format: `{"mineru_token": "your_token"}` or `{"token": "your_token"}`

## OpenCode Skill Integration

This project can be used as an [OpenCode](https://github.com/call0n3/opencode) skill. The skill directory is `~/.config/opencode/skills/mineru2md/` with `SKILL.md` and `mineru2md.py`. Token persists to `config.json` so it's entered once.
