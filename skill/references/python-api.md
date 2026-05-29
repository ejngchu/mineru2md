# Python API Reference

For most use cases, use the CLI:

```bash
mineru2md --file ./doc.pdf --print
```

## Script Mode (No Install)

```bash
MINERU_TOKEN='your_token' python ./src/mineru2md/cli.py --file ./doc.pdf --print
```

## Programmatic Usage

Import the CLI module directly:

```python
import sys
sys.path.insert(0, './src')

from mineru2md.cli import parse_with_auto_routing, get_token, MinerUError

# Get token (env var or config file)
token = get_token()

# Auto-route single file
md_content, filename, output_dir = parse_with_auto_routing(
    "./doc.pdf",
    token=token,
    optional_params={"enable_formula": True, "language": "en"}
)
```

## Config File

`~/.config/mineru2md/config.json` — auto-created on first run.

```json
{
  "mineru_token": ""
}
```
