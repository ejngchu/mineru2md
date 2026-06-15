# MinerU2MD

Convert PDF, images, Word, PowerPoint, Excel files and URLs to Markdown using [MinerU](https://mineru.net) APIs.

Auto-routes between **Lightweight API** (free, no token, ≤10MB/≤20 pages) and **Precision API** (token required).

## Install

```bash
pip install -e .
```

## Quick Start

```bash
# Single file — auto-selects API based on file size/pages
mineru2md --file ./doc.pdf --print

# Single URL
mineru2md --url https://example.com/article --print

# Batch files
mineru2md --files f1.pdf f2.png --output ./results/
```

## Token Setup

**Token is required for Precision API** (files >10MB, >20 pages, or HTML).

| Priority | Source |
|----------|--------|
| 1 | `MINERU_TOKEN` environment variable |
| 2 | `~/.config/mineru2md/config.json` |

**Config file** (`~/.config/mineru2md/config.json`) is auto-created on first run with your `MINERU_TOKEN` value pre-filled.

```json
{
  "mineru_token": "your_token"
}
```

Get a token from [mineru.net](https://mineru.net). The `Bearer ` prefix is added automatically.

## Supported Formats

| Format | Extensions | Lightweight | Precision |
|--------|-----------|:---:|:---:|
| PDF | `.pdf` | ≤20 pages, ≤10MB | ✅ |
| Images | `.png .jpg .jpeg .jp2 .webp .gif .bmp` | ≤10MB | ✅ |
| Word | `.docx` | ≤20 pages, ≤10MB | ✅ |
| PowerPoint | `.pptx` | ≤20 pages, ≤10MB | ✅ |
| Excel | `.xlsx` | ≤20 pages, ≤10MB | ✅ |
| HTML | `.html .htm` | ❌ | ✅ |

## Options

```bash
--file <path>           # Single file (auto-routes API)
--url <url>             # Single URL
--files <paths...>       # Batch files (Precision API)

--print                 # Output markdown to stdout instead of saving
--output <dir/>         # Output directory
--timestamp             # Prepend date to filename

--enable-formula        # Enable formula recognition
--enable-table          # Enable table recognition
--language <lang>       # Language code (default: ch)
--page-ranges <ranges>  # e.g. 1-10,15,20-25
--force-precision       # Force Precision API even for small files
--timeout <seconds>     # Polling timeout (default: 300)
```

## Script Mode (No Install)

```bash
MINERU_TOKEN='your_token' python ./src/mineru2md/cli.py --file ./doc.pdf --print
```

## Claude Code Skill

After `pip install -e .`, add to Claude Code:

```
/skills add mineru2md ./skill
```

## OpenCode Skill (One-Liner Install)

从 GitHub 仓库 https://github.com/ejngchu/mineru2md 下载代码到本地，识别 SKILL.md 并安装为当前平台的 skill，同时通过 pip install . 安装 CLI 工具，安装完成后删除临时文件。

```bash
git clone --depth=1 https://github.com/ejngchu/mineru2md /tmp/mineru2md_tmp && \
mkdir -p ~/.config/opencode/skills/mineru2md && \
cp -r /tmp/mineru2md_tmp/skill/* ~/.config/opencode/skills/mineru2md/ && \
cd /tmp/mineru2md_tmp && pip install . && \
rm -rf /tmp/mineru2md_tmp
```

## License

MIT
