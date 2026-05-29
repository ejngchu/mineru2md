# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

MinerU2MD converts PDF, images, Word, PowerPoint, Excel files and URLs to Markdown using [MinerU](https://mineru.net) APIs. Auto-routes between **Lightweight Agent API** (no token, ≤10MB, ≤20 pages) and **Precision API** (token required).

## Install

```bash
pip install -e .
```

## Commands

```bash
mineru2md --file ./doc.pdf --print
mineru2md --url https://example.com/article --print
mineru2md --files f1.pdf f2.pdf --output ./results/
```

## API Routing

| File Condition | API | Token |
|----------------|-----|-------|
| ≤10MB, ≤20 pages, supported type | Lightweight | No |
| >10MB OR >20 pages | Precision | Yes |

## Key Files

- `src/mineru2md/cli.py` — Main CLI and API logic (~1600 lines, well-sectioned)

## Testing

```bash
pytest tests/ -v           # All 45 tests
pytest tests/test_mineru2md.py::TestExtractFileExtension -v  # Single test class
```

## Token Config

Token loaded from (priority order):
1. `MINERU_TOKEN` environment variable
2. `~/.config/mineru2md/config.json` (all platforms)

Config file is auto-created on first run. Format: `{"mineru_token": ""}`

## OpenCode Skill Integration

This project can be used as an [OpenCode](https://github.com/call0n3/opencode) skill. The skill directory is `skill/` with `SKILL.md` and `references/`.
