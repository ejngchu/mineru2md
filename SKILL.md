---
name: mineru2md
description: Parse images and convert them to Markdown using mineru2md library. Use when user sends an image or multiple images and wants to extract content as markdown, or when user provides a screenshot/image file path to convert to text.
---

# mineru2md Image Parser

Use mineru2md to parse images and convert them to Markdown with persistent token management. Supports both single file and batch processing.

**Image Path Resolution**: When given a relative path, the skill prioritizes the current working directory (cwd) before other locations.

## Supported Formats

| Type | Extensions | Notes |
|------|-----------|-------|
| Images | `.png`, `.jpg`, `.jpeg`, `.jp2`, `.webp`, `.gif`, `.bmp` | ≤10MB use Lightweight API |
| PDF | `.pdf` | ≤10MB, ≤20 pages use Lightweight API |
| Word | `.docx` | ≤10MB, ≤20 pages |
| PowerPoint | `.pptx` | ≤10MB, ≤20 pages |
| Excel | `.xlsx` | ≤10MB, ≤20 pages |
| HTML | `.html`, `.htm` | Precision API only |

## File Structure

```
C:\Users\call0ns\.config\opencode\skills\mineru2md\
├── SKILL.md
├── mineru2md.py  (与 SKILL.md 同级目录)
└── config.json  (created automatically after first token entry)
```

## Token Management

### Token Configuration

**Important**: Never hardcode tokens. Always use environment variables.

The Precision API token is loaded from the `MINERU_TOKEN` environment variable.

**Token Environment Variable**:
- **Variable name**: `MINERU_TOKEN`
- **Usage**: Token for Precision API (required for images >= 10MB)

### Token Storage Location

- **Config file**: `C:\Users\call0ns\.config\opencode\skills\mineru2md\config.json`
- **Format**:
```json
{
  "precision_token": "your-saved-token-here"
}
```

## CLI Parameter Mapping

### Default Behavior

| User Intent | CLI Command |
|-------------|------------|
| 解析图片/转换图片 | `--file 图片 --print` |
| 批量解析图片 | `--files img1 img2 --print` |

### Save to Directory

| User Intent | CLI Command |
|-------------|------------|
| 保存结果 | `--file 图片` (不加 --print，使用默认输出) |
| 保存到指定目录 | `--file 图片 --output-dir 目录路径` |
| 批量保存到目录 | `--files img1 img2 --output-dir 目录路径` |

### Timestamp Filename

| User Intent | CLI Command |
|-------------|------------|
| 添加时间戳保存 | `--file 图片 --timestamp` (不加 --print) |
| 带时间戳保存到目录 | `--file 图片 --output-dir 目录路径 --timestamp` |

### Optional Parameters

| User Intent | CLI Command |
|-------------|------------|
| 启用公式识别 | `--enable-formula` |
| 禁用公式识别 | `--disable-formula` |
| 启用表格识别 | `--enable-table` |
| 禁用表格识别 | `--disable-table` |
| 启用 OCR | `--is-ocr` |
| 设置语言 (默认: ch) | `--language en` |
| 指定页码范围 | `--page-ranges 1-10,15,20-25` |
| 额外格式 (docx/html/latex) | `--extra-formats docx --extra-formats html` |
| 跳过缓存 | `--no-cache` |
| 设置缓存时间 (秒) | `--cache-tolerance 1800` |
| 设置超时 (默认: 300s) | `--timeout 600` |
| 强制 Precision API | `--force-precision` |

## Processing Flow

### Single File Processing

```
┌─────────────────────────────────────────────────────────────────┐
│                     mineru2md Image Parser                      │
│              图片 → Markdown 转换 (基于 MinerU)                   │
└─────────────────────────────────────────────────────────────────┘

                              │
                              ▼
              ┌───────────────────────────────┐
              │  1. 查找图片文件               │
              │  优先当前目录 (cwd)             │
              └───────────────────────────────┘
                              │
                              ▼
              ┌───────────────────────────────┐
              │  2. 检查文件大小                │
              │  < 10MB → Lightweight API     │
              │  >= 10MB → Precision API      │
              └───────────────────────────────┘
                              │
                    ┌─────────┴─────────┐
                    ▼                   ▼
            ┌──────────────┐    ┌──────────────┐
            │  < 10MB      │    │  >= 10MB     │
            │  无需 Token   │    │  需要 Token   │
            └──────────────┘    └──────────────┘
                    │                   │
                    │           ┌─────┴─────┐
                    │           ▼           ▼
                    │    ┌──────────┐  ┌──────────┐
                    │    │ Token存在 │  │ Token不存在│
                    │    └──────────┘  └──────────┘
                    │          │           │
                    │          │           ▼
                    │          │    提示用户输入Token
                    │          │           │
                    └──────────┴───────────┘
                              │
                              ▼
              ┌───────────────────────────────┐
              │  3. 执行解析                   │
              │  设置 MINERU_TOKEN 环境变量      │
              │  python mineru2md.py \        │
              │    --file 图片文件 [options]   │
              └───────────────────────────────┘
                              │
                              ▼
              ┌───────────────────────────────┐
              │  4. 返回结果                   │
              │  --print → stdout             │
              │  --output-dir → 保存到目录     │
              │  --timestamp → 带时间戳保存    │
              └───────────────────────────────┘
```

## CLI Commands Reference

### 1. Default: Parse & Print to Stdout

```bash
# 单文件 (默认使用 --print)
python mineru2md.py --file 图片.png --print

# 批量 (默认使用 --print)
python mineru2md.py --files img1.png img2.jpg --print
```

### 2. Save to Directory

```bash
# 保存到指定目录 (不使用 --print)
python mineru2md.py --file 图片.png --output-dir ./output

# 批量保存到目录
python mineru2md.py --files img1.png img2.jpg --output-dir ./output
```

### 3. Timestamp Filename

```bash
# 保存并添加时间戳 (不使用 --print)
python mineru2md.py --file 图片.png --timestamp

# 带时间戳保存到目录
python mineru2md.py --file 图片.png --output-dir ./output --timestamp
```

### 4. With Optional Parameters

```bash
# 启用公式和表格识别
python mineru2md.py --file doc.pdf --enable-formula --enable-table

# 设置语言
python mineru2md.py --file doc.pdf --language en

# 指定页码范围
python mineru2md.py --file doc.pdf --page-ranges 1-10,15,20-25

# OCR 识别
python mineru2md.py --file 图片.png --is-ocr

# 跳过缓存
python mineru2md.py --url https://example.com/doc.pdf --no-cache

# 强制使用 Precision API
python mineru2md.py --file small.pdf --force-precision
```

## Python API

### Token Management

```python
import json
import os
import subprocess
import sys
from pathlib import Path

SKILL_DIR = Path(r"C:\Users\call0ns\.config\opencode\skills\mineru2md")
CONFIG_FILE = SKILL_DIR / "config.json"
MINERU_SCRIPT = SKILL_DIR / "mineru2md.py"


def get_saved_token():
    """Load saved token from config file."""
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                config = json.load(f)
                return config.get("precision_token")
        except (json.JSONDecodeError, IOError) as e:
            print(f"Warning: Failed to read config file: {e}")
    return None


def save_token(token):
    """Save token to config file."""
    config = {}
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                config = json.load(f)
        except (json.JSONDecodeError, IOError):
            pass

    config["precision_token"] = token

    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)


def get_token():
    """Get token from MINERU_TOKEN environment variable."""
    return os.environ.get("MINERU_TOKEN")


def resolve_image_path(image_path):
    """
    Resolve image path, prioritizing current working directory.

    Resolution order:
    1. If absolute path exists, use it
    2. If relative path exists from current working directory, use it
    3. Return original path (let mineru2md handle the error)

    Args:
        image_path: User-provided image path (absolute or relative)

    Returns:
        Resolved absolute path or original path
    """
    p = Path(image_path)

    # If already absolute and exists, use it
    if p.is_absolute() and p.exists():
        return str(p)

    # If relative path exists from current directory, resolve it
    if not p.is_absolute():
        cwd_path = Path.cwd() / p
        if cwd_path.exists():
            return str(cwd_path.resolve())

    # Return original - mineru2md will error if not found
    return image_path


def get_file_size(path):
    """Get file size in bytes."""
    return os.path.getsize(path)


def check_files_need_token(file_paths):
    """
    Check if any file needs precision API token (>10MB).

    Args:
        file_paths: List of file paths

    Returns:
        tuple: (needs_token: bool, reason: str)
    """
    for path in file_paths:
        try:
            size_mb = get_file_size(path) / (1024 * 1024)
            if size_mb >= 10:
                return True, f"File {path} is {size_mb:.1f}MB >= 10MB"
        except OSError:
            continue
    return False, "All files are < 10MB"


def parse_image(image_path, options=None):
    """
    Parse an image file using CLI mode.

    Args:
        image_path: Path to the image file (absolute or relative)
        options: dict with keys:
            - print: bool (default True) - print to stdout instead of saving
            - output_dir: str - output directory
            - timestamp: bool (default False) - prepend date to filename
            - enable_formula: bool
            - enable_table: bool
            - is_ocr: bool
            - language: str
            - page_ranges: str
            - force_precision: bool

    Returns:
        Tuple (md_content, success, error_message)
    """
    if options is None:
        options = {}

    resolved_path = resolve_image_path(image_path)

    # Build command
    cmd = [
        sys.executable,
        str(MINERU_SCRIPT),
        "--file", resolved_path
    ]

    # Output mode selection
    if options.get("output_dir"):
        cmd.extend(["--output-dir", options["output_dir"]])

    if options.get("timestamp"):
        cmd.append("--timestamp")
    elif options.get("print", True):
        cmd.append("--print")

    # Optional parameters
    if options.get("enable_formula"):
        cmd.append("--enable-formula")
    if options.get("disable_formula"):
        cmd.append("--disable-formula")
    if options.get("enable_table"):
        cmd.append("--enable-table")
    if options.get("disable_table"):
        cmd.append("--disable-table")
    if options.get("is_ocr"):
        cmd.append("--is-ocr")
    if options.get("language"):
        cmd.extend(["--language", options["language"]])
    if options.get("page_ranges"):
        cmd.extend(["--page-ranges", options["page_ranges"]])
    if options.get("extra_formats"):
        for fmt in options["extra_formats"]:
            cmd.extend(["--extra-formats", fmt])
    if options.get("no_cache"):
        cmd.append("--no-cache")
    if options.get("cache_tolerance"):
        cmd.extend(["--cache-tolerance", str(options["cache_tolerance"])])
    if options.get("timeout"):
        cmd.extend(["--timeout", str(options["timeout"])])
    if options.get("force_precision"):
        cmd.append("--force-precision")

    # Set MINERU_TOKEN environment variable for subprocess
    token = get_saved_token()
    env = {**os.environ, "MINERU_TOKEN": token or ""}

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,
            env=env
        )

        if result.returncode == 0:
            return result.stdout, True, None
        else:
            return None, False, result.stderr

    except subprocess.TimeoutExpired:
        return None, False, "Timeout: parsing took too long"
    except Exception as e:
        return None, False, str(e)


def parse_batch(image_paths, options=None):
    """
    Parse multiple image files in batch using CLI mode.

    Args:
        image_paths: List of image file paths (absolute or relative)
        options: dict (same as parse_image)

    Returns:
        dict with keys:
            - success: bool
            - results: list of (md_content, filename, success, error)
            - token_needed: bool
            - error: str or None
    """
    if options is None:
        options = {}

    result = {
        "success": False,
        "results": [],
        "token_needed": False,
        "error": None
    }

    try:
        # Resolve all paths
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

        # Check if any file needs token
        needs_token, _ = check_files_need_token(resolved_paths)

        if needs_token:
            token = get_saved_token()
            if not token:
                result["token_needed"] = True
                return result

        # Build batch command
        cmd = [
            sys.executable,
            str(MINERU_SCRIPT),
            "--files"
        ] + resolved_paths

        # Output mode selection
        if options.get("output_dir"):
            cmd.extend(["--output-dir", options["output_dir"]])

        if options.get("timestamp"):
            cmd.append("--timestamp")
        elif options.get("print", True):
            cmd.append("--print")

        # Optional parameters
        if options.get("enable_formula"):
            cmd.append("--enable-formula")
        if options.get("disable_formula"):
            cmd.append("--disable-formula")
        if options.get("enable_table"):
            cmd.append("--enable-table")
        if options.get("disable_table"):
            cmd.append("--disable-table")
        if options.get("is_ocr"):
            cmd.append("--is-ocr")
        if options.get("language"):
            cmd.extend(["--language", options["language"]])
        if options.get("page_ranges"):
            cmd.extend(["--page-ranges", options["page_ranges"]])
        if options.get("force_precision"):
            cmd.append("--force-precision")

        # Set MINERU_TOKEN environment variable for subprocess
        token = get_saved_token()
        env = {**os.environ, "MINERU_TOKEN": token or ""}

        batch_result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600,  # Longer timeout for batch
            env=env
        )

        if batch_result.returncode == 0:
            result["success"] = True
            result["results"].append((batch_result.stdout, "batch", True, None))
        else:
            result["error"] = batch_result.stderr

    except Exception as e:
        result["error"] = f"Unexpected error: {e}"

    return result


def safe_parse_image(image_path, options=None):
    """
    Safely parse single image with automatic flow control.

    Args:
        image_path: Path to the image file
        options: dict (same as parse_image)

    Returns:
        dict with keys:
            - success: bool
            - md_content: str or None
            - token_needed: bool (True if user should be prompted for token)
            - error: str or None
    """
    if options is None:
        options = {}

    result = {
        "success": False,
        "md_content": None,
        "token_needed": False,
        "error": None
    }

    try:
        # Resolve image path
        resolved_path = resolve_image_path(image_path)

        if not os.path.exists(resolved_path):
            result["error"] = f"File not found: {resolved_path}"
            return result

        # Check file size for token requirement
        file_size = get_file_size(resolved_path)
        size_mb = file_size / (1024 * 1024)

        if size_mb >= 10:
            # Large file - token required
            token = get_saved_token()
            if not token:
                result["token_needed"] = True
                return result

        # Parse with token if needed
        md_content, success, error = parse_image(resolved_path, options)

        if success:
            result["success"] = True
            result["md_content"] = md_content
        else:
            result["error"] = error

    except Exception as e:
        result["error"] = f"Unexpected error: {e}"

    return result


def safe_parse_images(image_paths, options=None):
    """
    Safely parse multiple images with automatic flow control.

    Args:
        image_paths: List of image file paths
        options: dict (same as parse_image)

    Returns:
        dict with keys:
            - success: bool
            - results: list of (md_content, filename, success, error)
            - token_needed: bool
            - error: str or None
    """
    if options is None:
        options = {}

    result = {
        "success": False,
        "results": [],
        "token_needed": False,
        "error": None
    }

    try:
        # Resolve all paths and check existence
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

        # Check if any file needs token (>10MB)
        needs_token, _ = check_files_need_token(resolved_paths)

        if needs_token:
            token = get_saved_token()
            if not token:
                result["token_needed"] = True
                return result

        # Use batch processing
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


def parse_with_token(image_path, token, options=None):
    """
    Parse image with user-provided token.

    Args:
        image_path: Path to the image file
        token: Precision API token
        options: dict (same as parse_image)

    Returns:
        dict with keys:
            - success: bool
            - md_content: str or None
            - error: str or None
    """
    if options is None:
        options = {}

    result = {
        "success": False,
        "md_content": None,
        "error": None
    }

    try:
        # Save token for future use
        save_token(token)
        print(f"Token saved to {CONFIG_FILE}")

        # Resolve image path
        resolved_path = resolve_image_path(image_path)

        # Parse
        md_content, success, error = parse_image(resolved_path, options)

        if success:
            result["success"] = True
            result["md_content"] = md_content
        else:
            result["error"] = error

    except Exception as e:
        result["error"] = f"Unexpected error: {e}"

    return result


def parse_images_with_token(image_paths, token, options=None):
    """
    Parse multiple images with user-provided token.

    Args:
        image_paths: List of image file paths
        token: Precision API token
        options: dict (same as parse_image)

    Returns:
        dict with keys:
            - success: bool
            - results: list
            - error: str or None
    """
    if options is None:
        options = {}

    result = {
        "success": False,
        "results": [],
        "error": None
    }

    try:
        # Save token for future use
        save_token(token)
        print(f"Token saved to {CONFIG_FILE}")

        # Use batch processing
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

## User Intent Mapping

### Intent → CLI Options

| User Says | Parse Options |
|-----------|---------------|
| 解析图片 | `{print: True}` |
| 转换图片 | `{print: True}` |
| 把图片转成markdown | `{print: True}` |
| 保存结果 | `{}` (不加 --print) |
| 保存到指定目录 | `{output_dir: "目录路径"}` |
| 添加时间戳保存 | `{timestamp: True}` |
| 带时间戳保存 | `{timestamp: True, output_dir: "目录"}` |

## Return Value

### safe_parse_image / safe_parse_images

```python
{
    "success": bool,       # True if parsing succeeded
    "md_content": str,     # Markdown content (if success, single file)
    "results": list,       # List of results (if batch)
    "token_needed": bool,  # True if >=10MB and no token saved
    "error": str           # Error message (if failed)
}
```

### parse_with_token / parse_images_with_token

```python
{
    "success": bool,       # True if parsing succeeded
    "md_content": str,     # Markdown content (if success, single file)
    "results": list,       # List of results (if batch)
    "error": str           # Error message (if failed)
}
```

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `MINERU_TOKEN` | For >= 10MB images | Precision API token |

## Notes

- Default behavior: use `--print` (output to stdout)
- Save instruction: use `--output-dir` (directory only)
- Timestamp instruction: use `--timestamp` (NOT `--print`)
- Token is loaded from `MINERU_TOKEN` environment variable
- Batch mode uses `--files` flag with multiple file paths
- Once a token is saved, it is automatically loaded for subsequent uses