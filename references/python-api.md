# mineru2md Python API Reference

Use these Python functions to programmatically parse images and files via the mineru2md skill.

## Installation Paths

The skill is installed at `C:\Users\call0ns\.config\opencode\skills\mineru2md\`:

```python
from pathlib import Path

SKILL_DIR = Path(r"C:\Users\call0ns\.config\opencode\skills\mineru2md")
CONFIG_FILE = SKILL_DIR / "config.json"
MINERU_SCRIPT = SKILL_DIR / "scripts/mineru2md.py"
```

## Token Management

### `get_saved_token()`
Load saved token from config file.

```python
def get_saved_token():
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                config = json.load(f)
                return config.get("mineru_token")
        except (json.JSONDecodeError, IOError) as e:
            print(f"Warning: Failed to read config file: {e}")
    return None
```

### `save_token(token)`
Save token to config file.

```python
def save_token(token):
    config = {}
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                config = json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    config["mineru_token"] = token
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)
```

### `get_token()`
Get token from `MINERU_TOKEN` environment variable.

```python
def get_token():
    return os.environ.get("MINERU_TOKEN")
```

## Path Resolution

### `resolve_image_path(image_path)`
Resolve image path, prioritizing current working directory.

Resolution order:
1. If absolute path exists, use it
2. If relative path exists from current working directory, use it
3. Return original path (let mineru2md handle the error)

```python
def resolve_image_path(image_path):
    p = Path(image_path)
    if p.is_absolute() and p.exists():
        return str(p)
    if not p.is_absolute():
        cwd_path = Path.cwd() / p
        if cwd_path.exists():
            return str(cwd_path.resolve())
    return image_path
```

### `get_file_size(path)`
Get file size in bytes.

```python
def get_file_size(path):
    return os.path.getsize(path)
```

## File Check Utilities

### `check_files_need_token(file_paths)`
Check if any file needs precision API token (>10MB).

Returns `(needs_token: bool, reason: str)`.

```python
def check_files_need_token(file_paths):
    for path in file_paths:
        try:
            size_mb = get_file_size(path) / (1024 * 1024)
            if size_mb >= 10:
                return True, f"File {path} is {size_mb:.1f}MB >= 10MB"
        except OSError:
            continue
    return False, "All files are < 10MB"
```

## Single File Parsing

### `parse_image(image_path, options=None)`
Parse an image file using CLI mode. Returns `(md_content, success, error_message)`.

**Options dict keys:**
| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `print` | bool | `True` | Print to stdout instead of saving |
| `output_dir` | str | — | Output directory |
| `timestamp` | bool | `False` | Prepend date to filename |
| `enable_formula` | bool | — | Enable formula recognition |
| `enable_table` | bool | — | Enable table recognition |
| `is_ocr` | bool | — | Enable OCR |
| `language` | str | — | Document language (default: `ch`) |
| `page_ranges` | str | — | Page ranges (e.g. `"1-10,15,20-25"`) |
| `force_precision` | bool | — | Force Precision API |

```python
import os, subprocess, sys
from pathlib import Path

def parse_image(image_path, options=None):
    if options is None:
        options = {}

    resolved_path = resolve_image_path(image_path)

    cmd = [
        sys.executable,
        str(MINERU_SCRIPT),
        "--file", resolved_path
    ]

    if options.get("output_dir"):
        cmd.extend(["--output-dir", options["output_dir"]])
    if options.get("timestamp"):
        cmd.append("--timestamp")
    elif options.get("print", True):
        cmd.append("--print")

    if options.get("enable_formula"):     cmd.append("--enable-formula")
    if options.get("disable_formula"):    cmd.append("--disable-formula")
    if options.get("enable_table"):       cmd.append("--enable-table")
    if options.get("disable_table"):      cmd.append("--disable-table")
    if options.get("is_ocr"):             cmd.append("--is-ocr")
    if options.get("language"):           cmd.extend(["--language", options["language"]])
    if options.get("page_ranges"):        cmd.extend(["--page-ranges", options["page_ranges"]])
    if options.get("extra_formats"):
        for fmt in options["extra_formats"]:
            cmd.extend(["--extra-formats", fmt])
    if options.get("no_cache"):           cmd.append("--no-cache")
    if options.get("cache_tolerance"):    cmd.extend(["--cache-tolerance", str(options["cache_tolerance"])])
    if options.get("timeout"):            cmd.extend(["--timeout", str(options["timeout"])])
    if options.get("force_precision"):    cmd.append("--force-precision")

    token = get_saved_token()
    env = {**os.environ, "MINERU_TOKEN": token or ""}

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300, env=env)
        if result.returncode == 0:
            return result.stdout, True, None
        else:
            return None, False, result.stderr
    except subprocess.TimeoutExpired:
        return None, False, "Timeout: parsing took too long"
    except Exception as e:
        return None, False, str(e)
```

## Batch Parsing

### `parse_batch(image_paths, options=None)`
Parse multiple image files in batch using CLI mode.

Returns a dict:
```python
{
    "success": bool,
    "results": [(md_content, filename, success, error), ...],
    "token_needed": bool,
    "error": str or None
}
```

```python
def parse_batch(image_paths, options=None):
    if options is None:
        options = {}

    result = {"success": False, "results": [], "token_needed": False, "error": None}

    try:
        resolved_paths = []
        for path in image_paths:
            resolved = resolve_image_path(path)
            if not os.path.exists(resolved):
                result["results"].append((None, path, False, f"File not found: {resolved}"))
                continue
            resolved_paths.append(resolved)

        if not resolved_paths:
            result["error"] = "No valid files to process"
            return result

        needs_token, _ = check_files_need_token(resolved_paths)
        if needs_token:
            token = get_saved_token()
            if not token:
                result["token_needed"] = True
                return result

        cmd = [sys.executable, str(MINERU_SCRIPT), "--files"] + resolved_paths

        if options.get("output_dir"):
            cmd.extend(["--output-dir", options["output_dir"]])
        if options.get("timestamp"):
            cmd.append("--timestamp")
        elif options.get("print", True):
            cmd.append("--print")

        if options.get("enable_formula"):     cmd.append("--enable-formula")
        if options.get("disable_formula"):    cmd.append("--disable-formula")
        if options.get("enable_table"):       cmd.append("--enable-table")
        if options.get("disable_table"):      cmd.append("--disable-table")
        if options.get("is_ocr"):             cmd.append("--is-ocr")
        if options.get("language"):           cmd.extend(["--language", options["language"]])
        if options.get("page_ranges"):        cmd.extend(["--page-ranges", options["page_ranges"]])
        if options.get("force_precision"):    cmd.append("--force-precision")

        token = get_saved_token()
        env = {**os.environ, "MINERU_TOKEN": token or ""}

        batch_result = subprocess.run(cmd, capture_output=True, text=True, timeout=600, env=env)
        if batch_result.returncode == 0:
            result["success"] = True
            result["results"].append((batch_result.stdout, "batch", True, None))
        else:
            result["error"] = batch_result.stderr
    except Exception as e:
        result["error"] = f"Unexpected error: {e}"

    return result
```

## Safe Parsing with Auto Flow Control

### `safe_parse_image(image_path, options=None)`
Safely parse single image with automatic flow control. Checks file size, prompts for token if needed.

Returns:
```python
{
    "success": bool,
    "md_content": str or None,
    "token_needed": bool,  # True if >=10MB and no token saved
    "error": str or None
}
```

```python
def safe_parse_image(image_path, options=None):
    if options is None:
        options = {}

    result = {"success": False, "md_content": None, "token_needed": False, "error": None}

    try:
        resolved_path = resolve_image_path(image_path)
        if not os.path.exists(resolved_path):
            result["error"] = f"File not found: {resolved_path}"
            return result

        file_size = get_file_size(resolved_path)
        size_mb = file_size / (1024 * 1024)

        if size_mb >= 10:
            token = get_saved_token()
            if not token:
                result["token_needed"] = True
                return result

        md_content, success, error = parse_image(resolved_path, options)
        if success:
            result["success"] = True
            result["md_content"] = md_content
        else:
            result["error"] = error
    except Exception as e:
        result["error"] = f"Unexpected error: {e}"

    return result
```

### `safe_parse_images(image_paths, options=None)`
Safely parse multiple images with automatic flow control.

Returns:
```python
{
    "success": bool,
    "results": [(md_content, filename, success, error), ...],
    "token_needed": bool,
    "error": str or None
}
```

```python
def safe_parse_images(image_paths, options=None):
    if options is None:
        options = {}

    result = {"success": False, "results": [], "token_needed": False, "error": None}

    try:
        resolved_paths = []
        for path in image_paths:
            resolved = resolve_image_path(path)
            if not os.path.exists(resolved):
                result["results"].append((None, path, False, f"File not found: {resolved}"))
                continue
            resolved_paths.append(resolved)

        if not resolved_paths:
            result["error"] = "No valid files to process"
            return result

        needs_token, _ = check_files_need_token(resolved_paths)
        if needs_token:
            token = get_saved_token()
            if not token:
                result["token_needed"] = True
                return result

        batch_result = parse_batch(resolved_paths, options)
        if batch_result["token_needed"]:
            result["token_needed"] = True
            return result
        if batch_result["success"]:
            result["success"] = True
            result["results"] = batch_result["results"]
        else:
            result["error"] = batch_result["error"]
    except Exception as e:
        result["error"] = f"Unexpected error: {e}"

    return result
```

## Token-Provided Parsing

### `parse_with_token(image_path, token, options=None)`
Parse a single image with a user-provided token. Saves the token for future use.

Returns:
```python
{
    "success": bool,
    "md_content": str or None,
    "error": str or None
}
```

```python
def parse_with_token(image_path, token, options=None):
    if options is None:
        options = {}

    result = {"success": False, "md_content": None, "error": None}

    try:
        save_token(token)
        print(f"Token saved to {CONFIG_FILE}")
        resolved_path = resolve_image_path(image_path)
        md_content, success, error = parse_image(resolved_path, options)
        if success:
            result["success"] = True
            result["md_content"] = md_content
        else:
            result["error"] = error
    except Exception as e:
        result["error"] = f"Unexpected error: {e}"

    return result
```

### `parse_images_with_token(image_paths, token, options=None)`
Parse multiple images with a user-provided token. Saves the token for future use.

Returns:
```python
{
    "success": bool,
    "results": [(md_content, filename, success, error), ...],
    "error": str or None
}
```

```python
def parse_images_with_token(image_paths, token, options=None):
    if options is None:
        options = {}

    result = {"success": False, "results": [], "error": None}

    try:
        save_token(token)
        print(f"Token saved to {CONFIG_FILE}")
        batch_result = parse_batch(image_paths, options)
        if batch_result["success"]:
            result["success"] = True
            result["results"] = batch_result["results"]
        else:
            result["error"] = batch_result["error"]
    except Exception as e:
        result["error"] = f"Unexpected error: {e}"

    return result
```
