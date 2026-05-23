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
pytest tests/ -v  # 39 tests
```
