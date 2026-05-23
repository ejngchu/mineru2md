#!/usr/bin/env python3
"""
MinerU Converter - Convert files or URLs to markdown using MinerU APIs.

Auto-routes between Lightweight Agent API (no token needed) and Precision API (token needed)
based on file characteristics.
"""

import argparse
import glob as _glob
import io
import os
import re
import sys
import tempfile
import time
import uuid
import zipfile
from datetime import datetime
from urllib.parse import urlparse
from pathlib import Path
from typing import Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


# =============================================================================
# Configuration - API endpoints, limits, and timeouts
# =============================================================================

class APIConfig:
    """Centralized API configuration for MinerU services."""

    # Base URLs
    BASE_URL = "https://mineru.net"
    API_V4_BASE = f"{BASE_URL}/api/v4"
    AGENT_API_BASE = f"{BASE_URL}/api/v1/agent"

    # Precision API endpoints
    API_V4_FILE_URLS_BATCH = f"{API_V4_BASE}/file-urls/batch"
    API_V4_EXTRACT_TASK = f"{API_V4_BASE}/extract/task"
    API_V4_EXTRACT_TASK_ID = f"{API_V4_BASE}/extract/task/{{task_id}}"
    API_V4_EXTRACT_TASK_BATCH = f"{API_V4_BASE}/extract/task/batch"
    API_V4_EXTRACT_RESULTS_BATCH = f"{API_V4_BASE}/extract-results/batch/{{batch_id}}"

    # Lightweight Agent API endpoints
    AGENT_PARSE_URL = f"{AGENT_API_BASE}/parse/url"
    AGENT_PARSE_FILE = f"{AGENT_API_BASE}/parse/file"
    AGENT_QUERY_RESULT = f"{AGENT_API_BASE}/parse/{{task_id}}"

    # API Limits
    MAX_FILE_SIZE_MB = 200
    MAX_PRECISION_PAGES = 200
    LIGHTWEIGHT_MAX_PAGES = 20  # Lightweight API page limit
    LIGHTWEIGHT_MAX_SIZE_MB = 10
    MAX_BATCH_FILES = 50

    # Timeouts & Intervals (seconds)
    DEFAULT_TIMEOUT = 300
    POLL_INTERVAL = 3
    AGENT_POLL_INTERVAL = 2
    AGENT_DEFAULT_TIMEOUT = 180
    INITIAL_BACKOFF = 1
    MAX_RETRIES = 3

    # Lightweight API supported file extensions
    LIGHTWEIGHT_SUPPORTED_EXTENSIONS = {
        "pdf", "png", "jpg", "jpeg", "jp2", "webp", "gif", "bmp", "docx", "pptx", "xlsx"
    }


# =============================================================================
# Exceptions
# =============================================================================

class MinerUError(Exception):
    """Base exception for MinerU errors."""
    pass


# =============================================================================
# Error Codes
# =============================================================================

# Precision API error codes
ERROR_CODES = {
    "A0202": ("Token error", "Check that your MINERU_TOKEN is correct."),
    "A0211": ("Token expired", "Get a new token from MinerU dashboard."),
    "-500": ("Parameter error", "Ensure parameter types and Content-Type are correct."),
    "-10001": ("Service error", "Service temporarily unavailable. Try again later."),
    "-10002": ("Request parameter error", "Check your request parameters format."),
    "-60001": ("Upload URL generation failed", "Please try again later."),
    "-60002": ("File format matching failed", "Ensure filename has correct extension."),
    "-60003": ("File read failed", "The file may be corrupted."),
    "-60004": ("Empty file", "Please upload a valid non-empty file."),
    "-60005": ("File size exceeds limit", "Maximum file size is 200MB."),
    "-60006": ("Page count exceeds limit", "Maximum page count is 200."),
    "-60007": ("Model service unavailable", "Please try again later."),
    "-60008": ("File read timeout", "Check that the URL is accessible."),
    "-60009": ("Task queue full", "Please try again later."),
    "-60010": ("Parsing failed", "Please try again."),
    "-60011": ("Invalid file", "Ensure the file was uploaded successfully."),
    "-60012": ("Task not found", "Verify the task_id is valid."),
    "-60013": ("Access denied", "You can only access your own tasks."),
    "-60014": ("Cannot delete running task", "Running tasks cannot be deleted."),
    "-60015": ("File conversion failed", "Try converting to PDF manually."),
    "-60016": ("File conversion failed", "Try a different format or retry."),
    "-60017": ("Retry limit reached", "Wait and retry."),
    "-60018": ("Daily limit reached", "Try again tomorrow."),
    "-60019": ("HTML parsing quota exceeded", "Try again tomorrow."),
    "-60020": ("File splitting failed", "Please try again later."),
    "-60021": ("Page count reading failed", "Please try again later."),
    "-60022": ("Webpage read failed", "Check network or rate limiting."),
    "-60023": ("Invalid URL", "The URL is invalid or inaccessible."),
}

# Lightweight Agent API error codes
AGENT_ERROR_CODES = {
    "-30001": ("File too large", f"File exceeds {APIConfig.LIGHTWEIGHT_MAX_SIZE_MB}MB limit."),
    "-30002": ("Unsupported file type", "Use PDF/image/Docx/PPTx/Xlsx."),
    "-30003": ("Page count exceeds limit", f"File exceeds {APIConfig.LIGHTWEIGHT_MAX_PAGES} page limit."),
    "-30004": ("Request parameter error", "Check required parameters."),
}


# =============================================================================
# HTTP Session Management
# =============================================================================

_session = None


def get_session() -> requests.Session:
    """Get or create a requests.Session with connection pooling and retry."""
    global _session
    if _session is None:
        _session = requests.Session()
        adapter = HTTPAdapter(
            pool_connections=20,
            pool_maxsize=40,
            max_retries=Retry(
                total=3,
                backoff_factor=1,
                status_forcelist=[429, 500, 502, 503, 504],
                allowed_methods=["GET", "POST", "PUT", "HEAD"]
            )
        )
        _session.mount("https://", adapter)
        _session.mount("http://", adapter)
    return _session


def make_request_with_retry(
    method: str, url: str, headers: Optional[dict] = None,
    json: Optional[dict] = None, data: Optional[bytes] = None,
    max_retries: int = APIConfig.MAX_RETRIES,
    backoff: float = APIConfig.INITIAL_BACKOFF
) -> requests.Response:
    """Make HTTP request with retry on network/connection errors."""
    last_exception = None
    response = None
    session = get_session()

    for attempt in range(max_retries + 1):
        try:
            if method.upper() == "GET":
                response = session.get(url, headers=headers, json=json, timeout=60)
            elif method.upper() == "POST":
                response = session.post(url, headers=headers, json=json, data=data, timeout=60)
            elif method.upper() == "PUT":
                response = session.put(url, headers=headers, data=data, timeout=120)
            else:
                response = session.request(method, url, headers=headers, json=json, data=data, timeout=60)

            if 400 <= response.status_code < 500 and response.status_code != 429:
                return response
            return response

        except requests.exceptions.RequestException as e:
            last_exception = e
            if attempt < max_retries:
                wait_time = backoff * (2 ** attempt)
                print(f"  Request failed (attempt {attempt + 1}/{max_retries}): {e}. Retrying in {wait_time}s...")
                time.sleep(wait_time)

    print(f"  All {max_retries + 1} attempts failed.")
    if last_exception:
        raise last_exception
    if response is not None:
        return response
    raise MinerUError(f"All {max_retries + 1} requests failed with no response.")


def _check_response(response: requests.Response, context: str = "request") -> dict:
    """Check HTTP response and JSON body, raise MinerUError on failure."""
    if response.status_code != 200:
        msg = f"Error: {context} failed. Status: {response.status_code}"
        print(msg)
        if response.text:
            print(f"Response: {response.text[:1000]}")
        raise MinerUError(msg)

    result = response.json()
    if result.get("code") != 0:
        msg = parse_error_response(result)
        print(msg)
        raise MinerUError(msg)

    return result


def parse_error_response(result: dict) -> str:
    """Parse error code and message from API response."""
    code = str(result.get("code", ""))
    msg = result.get("msg", "Unknown error")

    if code in ERROR_CODES:
        error_name, error_hint = ERROR_CODES[code]
        return f"Error [{code}] {error_name}: {msg}. {error_hint}"
    elif code.startswith("A02"):
        return f"Error [{code}] Token error: {msg}. Check your MINERU_TOKEN."
    elif code.startswith("-6"):
        return f"Error [{code}] {msg}"
    return f"Error [{code}] {msg}"


# =============================================================================
# Utility Functions
# =============================================================================

def format_time(seconds: float) -> str:
    """Format seconds to mm:ss."""
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{minutes:02d}:{secs:02d}"


def _format_progress(elapsed: float, state: str, last_state: str, last_progress_update: float, prefix: str = "") -> tuple:
    """Print progress update and return (last_state, last_progress_update)."""
    if state != last_state or elapsed - last_progress_update >= 5:
        if state:
            print(f"\r[{format_time(elapsed)}]{prefix}{state.capitalize()}... ", end="", flush=True)
        else:
            print(f"\r[{format_time(elapsed)}] Waiting... ", end="", flush=True)
        return state, elapsed
    return last_state, last_progress_update


def extract_file_extension(filename: str) -> str:
    """Extract file extension from filename."""
    if "." in filename:
        return filename.rsplit(".", 1)[1].lower()
    return ""


def get_file_size_mb(file_path: str) -> float:
    """Get file size in megabytes."""
    size_bytes = os.path.getsize(file_path)
    return size_bytes / (1024 * 1024)


def get_page_count(file_path: str) -> Optional[int]:
    """Get page count for PDF files using PyMuPDF (fitz). Returns 0 for non-PDFs."""
    ext = extract_file_extension(file_path)
    if ext != "pdf":
        return 0

    try:
        import fitz
        doc = fitz.open(file_path)
        count = doc.page_count
        doc.close()
        return count
    except ImportError:
        print("  [Warning] PyMuPDF (fitz) not available. Page count unknown — will use Precision API.")
        return None
    except Exception as e:
        print(f"  [Warning] Failed to get page count ({e}) — will use Precision API.")
        return None


def extract_title(md_content: str) -> Optional[str]:
    """Extract the first level-1 heading from markdown to use as filename."""
    match = re.search(r'^#\s+(.+)$', md_content, re.MULTILINE)
    if match:
        title = match.group(1).strip()
        title = re.sub(r'[\\/:*?"<>|]', '_', title)
        title = title.strip().strip('.')
        if len(title) > 100:
            title = title[:100].rstrip()
        if not title:
            return None
        return title
    return None


def _url_has_file_extension(url: str) -> bool:
    """Check if URL path ends with a recognizable file extension for download."""
    parsed = urlparse(url)
    path = parsed.path.rstrip("/")
    last_seg = path.split("/")[-1] if "/" in path else ""
    ext_match = re.search(r'\.([a-zA-Z]{2,5})$', last_seg)
    if not ext_match:
        return False
    ext = ext_match.group(1).lower()
    download_extensions = {"pdf", "png", "jpg", "jpeg", "jp2", "webp", "gif", "bmp",
                          "docx", "pptx", "xlsx", "doc", "ppt", "xls"}
    return ext in download_extensions


def determine_model_version(filename_or_url: str, is_url: bool = False) -> str:
    """Determine model version based on file extension or URL."""
    if is_url:
        if _url_has_file_extension(filename_or_url):
            return "vlm"
        return "MinerU-HTML"
    else:
        ext = extract_file_extension(filename_or_url)
        if ext in {"html", "htm"}:
            return "MinerU-HTML"
        return "vlm"


def _apply_timestamp(output_path: str) -> str:
    """Prepend current date (YYYY-MM-DD) to the output filename."""
    date_prefix = datetime.now().strftime("%Y-%m-%d ")
    parent = os.path.dirname(output_path)
    basename = os.path.basename(output_path)
    new_name = date_prefix + basename
    if parent:
        return os.path.join(parent, new_name)
    return new_name


def save_markdown(content: str, output_path: str) -> None:
    """Save markdown content to file."""
    output_dir = os.path.dirname(output_path)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"[Save] Markdown saved to: {output_path}")


def generate_output_filename(input_path: str, is_url: bool = False) -> str:
    """Generate output filename from input path or URL."""
    if is_url:
        url_part = input_path.split("/")[-1].split("?")[0]
        if "." in url_part:
            filename = url_part.rsplit(".", 1)[0] + ".md"
        else:
            filename = url_part + ".md"
    else:
        basename = os.path.basename(input_path)
        if "." in basename:
            name_part, _, ext = basename.rpartition(".")
            if re.match(r'^[a-zA-Z]{2,5}$', ext):
                filename = name_part + ".md"
            else:
                filename = basename + ".md"
        else:
            filename = basename + ".md"

    return filename


# =============================================================================
# Routing Logic
# =============================================================================

def is_lightweight_compatible(file_path: str) -> bool:
    """Check if file qualifies for the Lightweight Agent API."""
    ext = extract_file_extension(file_path)
    if ext not in APIConfig.LIGHTWEIGHT_SUPPORTED_EXTENSIONS:
        return False

    size_mb = get_file_size_mb(file_path)
    if size_mb > APIConfig.LIGHTWEIGHT_MAX_SIZE_MB:
        return False

    pages = get_page_count(file_path)
    if pages is None:
        return False
    if pages > APIConfig.LIGHTWEIGHT_MAX_PAGES:
        return False

    return True


def get_routing_decision(file_path: str, force_precision: bool = False) -> tuple[str, str]:
    """Determine which API to use and return (api_type, reason)."""
    if force_precision:
        return 'precision', "forced via --force-precision"

    if is_lightweight_compatible(file_path):
        return 'lightweight', "no token needed"

    reasons = []
    ext = extract_file_extension(file_path)
    if ext not in APIConfig.LIGHTWEIGHT_SUPPORTED_EXTENSIONS:
        reasons.append("unsupported file type")

    size_mb = get_file_size_mb(file_path)
    if size_mb > APIConfig.LIGHTWEIGHT_MAX_SIZE_MB:
        reasons.append(f"file size {size_mb:.1f}MB > {APIConfig.LIGHTWEIGHT_MAX_SIZE_MB}MB")

    pages = get_page_count(file_path)
    if pages is not None and pages > APIConfig.LIGHTWEIGHT_MAX_PAGES:
        reasons.append(f"page count {pages} > {APIConfig.LIGHTWEIGHT_MAX_PAGES}")
    elif pages is None:
        reasons.append("cannot determine page count")

    reason_str = "; ".join(reasons) if reasons else "default"
    return 'precision', reason_str


def validate_file_for_api(file_path: str) -> list:
    """Validate file against Precision API limits before submission."""
    issues = []

    if not os.path.exists(file_path):
        return [f"File not found: {file_path}"]

    size_mb = get_file_size_mb(file_path)
    if size_mb > APIConfig.MAX_FILE_SIZE_MB:
        issues.append(f"File size {size_mb:.1f}MB exceeds {APIConfig.MAX_FILE_SIZE_MB}MB limit.")

    pages = get_page_count(file_path)
    if pages is not None and pages > APIConfig.MAX_PRECISION_PAGES:
        issues.append(f"Page count {pages} exceeds {APIConfig.MAX_PRECISION_PAGES} page limit.")

    return issues


def validate_batch_count(file_count: int) -> list:
    """Validate batch file count against API limits."""
    issues = []
    if file_count > APIConfig.MAX_BATCH_FILES:
        issues.append(f"Batch size {file_count} exceeds {APIConfig.MAX_BATCH_FILES} file limit.")
    return issues


# =============================================================================
# Lightweight Agent API Functions
# =============================================================================

def lightweight_parse_by_file(file_path: str, **kwargs) -> str:
    """Submit a local file to Lightweight Agent API. Returns task_id."""
    filename = os.path.basename(file_path)

    payload = {"file_name": filename}
    if kwargs:
        # Only include params that Agent API supports
        agent_params = {k: v for k, v in kwargs.items()
                       if k in ("page_range", "enable_formula", "enable_table", "language")}
        payload.update(agent_params)

    print(f"[Lightweight API] Submitting file: {filename}")
    session = get_session()
    response = session.post(APIConfig.AGENT_PARSE_FILE, json=payload, timeout=60)

    if response.status_code != 200:
        print(f"Error: Lightweight API request failed. Status: {response.status_code}")
        print(f"Response: {response.text}")
        raise MinerUError(f"Lightweight API request failed. Status: {response.status_code}")

    result = response.json()
    code = str(result.get("code", ""))
    msg = result.get("msg", "")

    if code in AGENT_ERROR_CODES:
        error_name, error_hint = AGENT_ERROR_CODES[code]
        print(f"Error [{code}] {error_name}: {msg}. {error_hint}")
        if code == "-30001":
            print("  File too large for lightweight API. Use Precision API instead.")
        elif code == "-30003":
            print("  Page count too high. Use Precision API or specify page_range.")
        raise MinerUError(f"Error [{code}] {error_name}: {msg}. {error_hint}")
    elif code != "0":
        print(f"Error [{code}]: {msg}")
        raise MinerUError(f"Error [{code}]: {msg}")

    task_id = result["data"]["task_id"]
    file_url = result["data"]["file_url"]
    print(f"[Lightweight API] Task ID: {task_id}")

    print(f"[Lightweight API] Uploading file to OSS...")
    with open(file_path, "rb") as f:
        upload_response = session.put(file_url, data=f, timeout=120)

    if upload_response.status_code not in (200, 201):
        print(f"Error: File upload failed. Status: {upload_response.status_code}")
        print(f"Response: {upload_response.text}")
        raise MinerUError(f"File upload failed. Status: {upload_response.status_code}")

    print(f"[Lightweight API] File uploaded successfully.")
    return task_id


def lightweight_parse_by_url(url: str, **kwargs) -> str:
    """Submit a URL to Lightweight Agent API. Returns task_id."""
    payload = {"url": url}
    if kwargs:
        # Only include params that Agent API supports
        agent_params = {k: v for k, v in kwargs.items()
                       if k in ("page_range", "enable_formula", "enable_table", "language")}
        payload.update(agent_params)

    print(f"[Lightweight API] Submitting URL: {url}")
    session = get_session()
    response = session.post(APIConfig.AGENT_PARSE_URL, json=payload, timeout=60)

    if response.status_code != 200:
        print(f"Error: Lightweight API URL request failed. Status: {response.status_code}")
        print(f"Response: {response.text}")
        raise MinerUError(f"Lightweight API URL request failed. Status: {response.status_code}")

    result = response.json()
    code = str(result.get("code", ""))
    msg = result.get("msg", "")

    if code in AGENT_ERROR_CODES:
        error_name, error_hint = AGENT_ERROR_CODES[code]
        print(f"Error [{code}] {error_name}: {msg}. {error_hint}")
        raise MinerUError(f"Error [{code}] {error_name}: {msg}. {error_hint}")
    elif code != "0":
        print(f"Error [{code}]: {msg}")
        raise MinerUError(f"Error [{code}]: {msg}")

    task_id = result["data"]["task_id"]
    print(f"[Lightweight API] Task ID: {task_id}")
    return task_id


def lightweight_poll_result(task_id: str, timeout: int = APIConfig.AGENT_DEFAULT_TIMEOUT) -> str:
    """Poll Lightweight Agent API for parsing results. Returns markdown content."""
    url = APIConfig.AGENT_QUERY_RESULT.format(task_id=task_id)
    start_time = time.time()
    last_state = None
    last_progress_update = 0

    print(f"[Lightweight API] Polling task: {task_id}")

    while True:
        elapsed = time.time() - start_time
        if elapsed >= timeout:
            print(f"\nError: Lightweight API polling timed out after {timeout} seconds.")
            raise MinerUError(f"Lightweight API polling timed out after {timeout} seconds.")

        try:
            response = make_request_with_retry("GET", url)
        except requests.exceptions.RequestException as e:
            print(f"\nError: Request failed: {e}")
            time.sleep(APIConfig.AGENT_POLL_INTERVAL)
            continue

        if response.status_code == 429:
            wait = APIConfig.AGENT_POLL_INTERVAL * 2
            print(f"\r[{format_time(elapsed)}] Rate limited. Waiting {wait}s... ", end="", flush=True)
            time.sleep(wait)
            continue

        if response.status_code != 200:
            print(f"\nError: Failed to query lightweight API status. Status: {response.status_code}")
            print(f"Response: {response.text}")
            raise MinerUError(f"Failed to query lightweight API status. Status: {response.status_code}")

        result = response.json()
        code = str(result.get("code", ""))

        if code in AGENT_ERROR_CODES:
            error_name, error_hint = AGENT_ERROR_CODES[code]
            print(f"\nError [{code}] {error_name}: {result.get('msg', '')}. {error_hint}")
            raise MinerUError(f"Error [{code}] {error_name}: {result.get('msg', '')}. {error_hint}")
        elif code != "0":
            print(f"\nError [{code}]: {result.get('msg', '')}")
            raise MinerUError(f"Error [{code}]: {result.get('msg', '')}")

        data = result.get("data", {})
        state = data.get("state", "")

        last_state, last_progress_update = _format_progress(
            elapsed, state, last_state, last_progress_update, prefix="Lightweight: ")

        if state == "done":
            print(f"\r[{format_time(elapsed)}] Done!                              ")
            markdown_url = data.get("markdown_url")
            if markdown_url:
                md_response = make_request_with_retry("GET", markdown_url)
                if md_response.status_code == 200:
                    return md_response.text
                else:
                    print(f"\nError: Failed to download markdown, status: {md_response.status_code}")
                    raise MinerUError(f"Failed to download markdown from {markdown_url}")

            markdown = (
                data.get("markdown") or
                data.get("result", {}).get("markdown") or
                data.get("full_markdown") or
                ""
            )
            if not markdown:
                print("\nError: Task done but no markdown content found in response.")
                print(f"Response data keys: {list(data.keys())}")
                raise MinerUError("Task done but no markdown content found in response.")
            return markdown

        elif state == "failed":
            print(f"\nError: Task failed. Reason: {data.get('err_msg', 'Unknown error')}")
            raise MinerUError(f"Task failed. Reason: {data.get('err_msg', 'Unknown error')}")

        elif state in ("pending", "running", "converting", "waiting-file", "uploading"):
            time.sleep(APIConfig.AGENT_POLL_INTERVAL)
        else:
            if state:
                print(f"\nUnknown state: {state}")
            time.sleep(APIConfig.AGENT_POLL_INTERVAL)


def lightweight_file_mode(file_path: str, optional_params: dict, output_dir: Optional[str] = None) -> tuple:
    """Handle lightweight API file mode end-to-end."""
    task_id = lightweight_parse_by_file(file_path, **optional_params)
    md_content = lightweight_poll_result(task_id)
    filename = os.path.basename(file_path)
    return md_content, filename, output_dir


def lightweight_url_mode(url: str, optional_params: dict, output_dir: Optional[str] = None) -> tuple:
    """Handle lightweight API URL mode end-to-end."""
    task_id = lightweight_parse_by_url(url, **optional_params)
    md_content = lightweight_poll_result(task_id)
    filename = url.split("/")[-1].split("?")[0]
    return md_content, filename, output_dir


# =============================================================================
# Precision API Functions
# =============================================================================

def get_headers(token: str) -> dict:
    """Get headers with authorization."""
    return {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}"
    }


def download_and_extract(
    zip_url: str, token: str, original_filename: str,
    output_dir: Optional[str] = None
) -> tuple:
    """Download zip, extract full.md and images/, rewrite paths. Returns (md_content, filename, output_dir)."""
    print(f"\n[Download] Downloading result from: {zip_url}")

    headers = {"Authorization": f"Bearer {token}"} if token else {}
    tmp_path = None
    session = get_session()
    response_body_prefix = ""

    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix='.zip') as tmp:
            tmp_path = tmp.name
            with session.get(zip_url, headers=headers, timeout=120, stream=True) as response:
                if response.status_code != 200:
                    print(f"Error: Failed to download zip. Status: {response.status_code}")
                    raise MinerUError(f"Failed to download zip. Status: {response.status_code}")

                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        tmp.write(chunk)
                        if not response_body_prefix:
                            try:
                                response_body_prefix = chunk[:500].decode("utf-8", errors="replace")
                            except Exception:
                                response_body_prefix = f"<binary chunk of {len(chunk)} bytes>"

        print(f"[Download] Downloaded to temp file: {tmp_path}")

        with zipfile.ZipFile(tmp_path) as zf:
            file_list = zf.namelist()
            print(f"[Extract] Zip contains {len(file_list)} files: {file_list}")

            full_md_name = None
            for name in file_list:
                if name.lower() == "full.md":
                    full_md_name = name
                    break

            if not full_md_name:
                print(f"Error: full.md not found in zip. Files: {file_list}")
                raise MinerUError("full.md not found in zip")

            with zf.open(full_md_name) as md_file:
                md_content = md_file.read().decode("utf-8")

            print(f"[Extract] Extracted full.md ({len(md_content)} bytes)")

            images_dir = None
            for name in file_list:
                if name.startswith("images/") or name.startswith("images\\"):
                    if images_dir is None:
                        if output_dir:
                            images_dir = os.path.join(output_dir, "images")
                        else:
                            images_dir = os.path.join(os.path.dirname(original_filename) or ".", "images")
                        os.makedirs(images_dir, exist_ok=True)
                        print(f"[Extract] Extracting images to: {images_dir}")

                    img_data = zf.read(name)
                    img_filename = os.path.basename(name.replace("\\", "/"))
                    img_path = os.path.join(images_dir, img_filename)
                    with open(img_path, "wb") as img_file:
                        img_file.write(img_data)

            if images_dir:
                image_count = len([n for n in file_list if n.startswith("images/") or n.startswith("images\\")])
                print(f"[Extract] Extracted {image_count} image(s)")

                if output_dir:
                    rel_images_path = os.path.relpath(images_dir, output_dir)
                else:
                    md_dir = os.path.dirname(original_filename) if os.path.dirname(original_filename) else "."
                    rel_images_path = os.path.relpath(images_dir, md_dir)

                md_content = re.sub(
                    r'!\[([^\]]*)\]\((?:\./)?(images/[^\)]+)\)',
                    f'![\\1]({rel_images_path}/\\2)',
                    md_content
                )

            return md_content, original_filename, output_dir

    except zipfile.BadZipFile:
        print("Error: Downloaded file is not a valid zip file.")
        if response_body_prefix:
            print(f"Content (first 500 chars): {response_body_prefix}")
        raise MinerUError("Downloaded file is not a valid zip file.")
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError as e:
                print(f"  [Warning] Could not delete temp file {tmp_path}: {e}")


def upload_file_mode(
    file_path: str, token: str, optional_params: dict,
    output_dir: Optional[str] = None, timeout: int = APIConfig.DEFAULT_TIMEOUT
) -> tuple:
    """Handle file upload mode: get upload URL, PUT file, poll results."""
    issues = validate_file_for_api(file_path)
    if issues:
        for issue in issues:
            print(f"  [Warning] {issue}")
        if any("exceeds" in i for i in issues):
            print("  Aborting due to limit violations.")
            raise MinerUError("; ".join(issues))

    filename = os.path.basename(file_path)
    data_id = str(uuid.uuid4())[:8]

    print(f"[File Mode] Processing: {filename}")
    print(f"[File Mode] Data ID: {data_id}")

    model_version = determine_model_version(filename)
    print(f"[File Mode] Model version: {model_version}")

    files_payload = [{"name": filename, "data_id": data_id}]
    payload = {
        "files": files_payload,
        "model_version": model_version
    }
    payload.update({k: v for k, v in optional_params.items() if k in [
        "enable_formula", "enable_table", "language", "extra_formats"
    ]})

    if "page_ranges" in optional_params:
        files_payload[0]["page_ranges"] = optional_params["page_ranges"]
    if "is_ocr" in optional_params:
        files_payload[0]["is_ocr"] = optional_params["is_ocr"]

    headers = get_headers(token)
    print(f"[File Mode] Requesting upload URL...")
    result = _check_response(
        make_request_with_retry("POST", APIConfig.API_V4_FILE_URLS_BATCH, headers=headers, json=payload),
        context="get upload URL"
    )

    batch_id = result["data"]["batch_id"]
    upload_url = result["data"]["file_urls"][0]
    print(f"[File Mode] Got upload URL. Batch ID: {batch_id}")

    print(f"[File Mode] Uploading file...")
    with open(file_path, "rb") as f:
        upload_response = make_request_with_retry("PUT", upload_url, data=f)

    if upload_response.status_code != 200:
        msg = f"Error: Failed to upload file. Status: {upload_response.status_code}"
        print(msg)
        if upload_response.text:
            print(f"Response: {upload_response.text[:500]}")
        raise MinerUError(msg)

    print(f"[File Mode] File uploaded successfully.")
    return poll_batch_results(batch_id, token, filename, timeout=timeout, output_dir=output_dir)


def submit_single_url_task(url: str, token: str, optional_params: dict) -> str:
    """Submit a single URL for extraction. Returns task_id."""
    headers = get_headers(token)
    model_version = determine_model_version(url, is_url=True)

    payload = {
        "url": url,
        "model_version": model_version
    }
    payload.update({k: v for k, v in optional_params.items() if k in [
        "enable_formula", "enable_table", "language", "extra_formats", "no_cache", "cache_tolerance"
    ]})

    result = _check_response(
        make_request_with_retry("POST", APIConfig.API_V4_EXTRACT_TASK, headers=headers, json=payload),
        context="submit URL task"
    )

    task_id = result["data"]["task_id"]
    return task_id


def submit_url_task(url: str, token: str, optional_params: dict) -> str:
    """Submit URL for extraction. Returns batch_id."""
    headers = get_headers(token)
    data_id = str(uuid.uuid4())[:8]
    model_version = determine_model_version(url, is_url=True)

    payload = {
        "files": [{"url": url, "data_id": data_id}],
        "model_version": model_version
    }
    payload.update({k: v for k, v in optional_params.items() if k in [
        "enable_formula", "enable_table", "language", "extra_formats", "no_cache", "cache_tolerance"
    ]})

    result = _check_response(
        make_request_with_retry("POST", APIConfig.API_V4_EXTRACT_TASK_BATCH, headers=headers, json=payload),
        context="submit URL task"
    )

    batch_id = result["data"]["batch_id"]
    return batch_id


def poll_single_task(
    task_id: str, token: str, filename: str,
    timeout: int = APIConfig.DEFAULT_TIMEOUT, output_dir: Optional[str] = None
) -> tuple:
    """Poll for single task results. Returns (md_content, filename, output_dir)."""
    headers = get_headers(token)
    url = APIConfig.API_V4_EXTRACT_TASK_ID.format(task_id=task_id)

    print(f"[Single Task Mode] Polling task: {task_id}")
    return _poll_single(url, headers, timeout, filename, token, output_dir=output_dir)


def _poll_single(
    url: str, headers: dict, timeout: int,
    filename: str, token: str, output_dir: Optional[str]
) -> tuple:
    """Poll single task results. Returns (md_content, filename, output_dir)."""
    start_time = time.time()
    last_state = None
    last_progress_update = 0

    while True:
        elapsed = time.time() - start_time
        if elapsed >= timeout:
            print(f"\nError: Polling timed out after {timeout} seconds.")
            raise MinerUError(f"Polling timed out after {timeout} seconds.")

        result = _check_response(
            make_request_with_retry("GET", url, headers=headers),
            context="poll task"
        )

        data = result.get("data", {})
        state = data.get("state", "")

        last_state, last_progress_update = _format_progress(
            elapsed, state, last_state, last_progress_update)

        if state == "done":
            print(f"\r[{format_time(elapsed)}] Done!                              ")
            full_zip_url = data.get("full_zip_url")
            if full_zip_url:
                return download_and_extract(full_zip_url, token, filename, output_dir=output_dir)
            err_code = data.get("err_code") or data.get("err")
            if err_code:
                raise MinerUError(f"Task failed with error code: {err_code}")
            raise MinerUError("Task done but no full_zip_url returned.")

        elif state == "failed":
            err_msg = data.get("err_msg", "Unknown error")
            print(f"\nError: Task failed. Reason: {err_msg}")
            raise MinerUError(f"Task failed. Reason: {err_msg}")

        elif state in ("pending", "running", "converting", "waiting-file", "uploading"):
            time.sleep(APIConfig.POLL_INTERVAL)
        else:
            if state:
                print(f"\nUnknown state: {state}")
            time.sleep(APIConfig.POLL_INTERVAL)


def url_mode(
    url: str, token: str, optional_params: dict,
    output_dir: Optional[str] = None, timeout: int = APIConfig.DEFAULT_TIMEOUT
) -> tuple:
    """Handle URL mode: submit URL, poll results."""
    print(f"[URL Mode] Processing: {url}")

    # Article URLs (no file extension) use single task endpoint for reliability
    if not _url_has_file_extension(url):
        print("[URL Mode] Using single task endpoint for article URL")
        task_id = submit_single_url_task(url, token, optional_params)
        print(f"[URL Mode] Task ID: {task_id}")
        filename = url.split("/")[-1].split("?")[0] if "/" in url else url
        return poll_single_task(task_id, token, filename, timeout=timeout, output_dir=output_dir)
    else:
        # File URLs use batch endpoint
        batch_id = submit_url_task(url, token, optional_params)
        print(f"[URL Mode] Batch ID: {batch_id}")
        filename = url.split("/")[-1].split("?")[0] if "/" in url else url
        return poll_batch_results(batch_id, token, filename, timeout=timeout, output_dir=output_dir)


def poll_batch_results(
    batch_id: str, token: str, filename: str,
    timeout: int = APIConfig.DEFAULT_TIMEOUT, output_dir: Optional[str] = None
) -> tuple:
    """Poll for batch results. Returns (md_content, filename, output_dir)."""
    headers = get_headers(token)
    url = APIConfig.API_V4_EXTRACT_RESULTS_BATCH.format(batch_id=batch_id)

    print(f"[Batch Mode] Polling batch: {batch_id}")
    return _poll_batch(url, headers, timeout, filename, token, output_dir=output_dir)


def _poll_loop(
    url: str, headers: dict, timeout: int, token: str,
    filename: str, output_dir: Optional[str],
    extract_state, context: str = "task"
) -> tuple:
    """Core polling loop. Returns (md_content, filename, output_dir)."""
    start_time = time.time()
    last_state = None
    last_progress_update = 0

    while True:
        elapsed = time.time() - start_time
        if elapsed >= timeout:
            print(f"\nError: Polling timed out after {timeout} seconds.")
            raise MinerUError(f"Polling timed out after {timeout} seconds.")

        result = _check_response(
            make_request_with_retry("GET", url, headers=headers),
            context=f"poll {context}"
        )

        data = result["data"]
        action, value = extract_state(data)

        if action == "done":
            if value:
                return download_and_extract(value, token, filename, output_dir=output_dir)
            print("\nError: Task done but no result URL returned.")
            raise MinerUError("Task done but no result URL returned.")
        elif action == "failed":
            print(f"\nError: Task failed. Reason: {value}")
            raise MinerUError(f"Task failed. Reason: {value}")
        elif action == "waiting":
            last_state, last_progress_update = _format_progress(
                elapsed, value, last_state, last_progress_update)
            time.sleep(APIConfig.POLL_INTERVAL)
        else:
            if value:
                print(f"\nUnknown state: {value}")
            time.sleep(APIConfig.POLL_INTERVAL)


def _poll_batch(
    url: str, headers: dict, timeout: int,
    filename: str, token: str, output_dir: Optional[str] = None
) -> tuple:
    """Poll batch results. Returns (md_content, filename, output_dir)."""
    def extract_state(data):
        extract_results = data.get("extract_result", [])
        if not extract_results:
            return ("waiting", "Waiting for results...")

        file_result = extract_results[0]
        state = file_result.get("state")
        file_name = file_result.get("file_name", filename)

        if state == "done":
            return ("done", file_result.get("full_zip_url"))
        elif state == "failed":
            return ("failed", file_result.get("err_msg", "Unknown error"))
        elif state in ("pending", "running", "converting", "waiting-file"):
            progress_str = f"{state.capitalize()}"
            if state == "running" and "extract_progress" in file_result:
                p = file_result["extract_progress"]
                progress_str += f" - Extracted {p.get('extracted_pages', 0)}/{p.get('total_pages', '?')} pages"
            return ("waiting", progress_str)
        return ("unknown", state)

    return _poll_loop(url, headers, timeout, token, filename, output_dir, extract_state, context="batch")


# =============================================================================
# Auto-Routing Business Logic
# =============================================================================

def parse_with_auto_routing(
    file_path_or_url: str,
    token: Optional[str],
    optional_params: dict,
    is_url: bool = False,
    force_precision: bool = False,
    output_dir: Optional[str] = None,
    timeout: int = APIConfig.DEFAULT_TIMEOUT
) -> tuple:
    """Main routing function that auto-selects between Lightweight and Precision API."""
    if is_url:
        # Article URLs (no file extension) use Precision API directly - Agent API doesn't support HTML
        # Direct file URLs use Precision API only
        if not _url_has_file_extension(file_path_or_url):
            print(f"[Route] Using Precision API (article URL)")
            if token is None:
                token = get_token()
            return url_mode(file_path_or_url, token, optional_params, output_dir=output_dir, timeout=timeout)
        elif force_precision:
            print(f"[Route] Using Precision API (forced)")
            return url_mode(file_path_or_url, token, optional_params, output_dir=output_dir, timeout=timeout)
        else:
            print(f"[Route] Using Precision API (file URL)")
            return url_mode(file_path_or_url, token, optional_params, output_dir=output_dir, timeout=timeout)

    api_type, reason = get_routing_decision(file_path_or_url, force_precision)
    print(f"[Route] Using {'Precision' if api_type == 'precision' else 'Lightweight'} API ({reason})")

    if api_type == 'lightweight':
        return lightweight_file_mode(file_path_or_url, optional_params, output_dir=output_dir)
    else:
        return upload_file_mode(file_path_or_url, token, optional_params, output_dir=output_dir, timeout=timeout)


def get_token() -> str:
    """Get API token from environment variable or config file.

    Priority:
    1. MINERU_TOKEN environment variable
    2. ~/.config/mineru2md/config.json (Linux/macOS)
    3. %APPDATA%/mineru2md/config.json (Windows)
    """
    # First try environment variable
    token = os.environ.get("MINERU_TOKEN")
    if token and token.strip():
        return token.strip()

    # Then try config file
    config_path = _get_config_path()
    if config_path and config_path.exists():
        try:
            import json
            with open(config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
                token = config.get("mineru_token") or config.get("token")
                if token and token.strip():
                    return token.strip()
        except (json.JSONDecodeError, IOError):
            pass

    raise MinerUError(
        "MINERU_TOKEN environment variable is not set, and no config file found. "
        f"Set MINERU_TOKEN or create config at {_get_config_path()}"
    )


def _get_config_path() -> Optional[Path]:
    """Get platform-specific config file path."""
    if sys.platform == "win32" or os.name == "nt":
        base = Path(os.environ.get("APPDATA", ""))
        return base / "mineru2md" / "config.json"
    else:
        return Path.home() / ".config" / "mineru2md" / "config.json"


def _batch_upload_and_poll(
    file_paths: list, token: str, optional_params: dict,
    output_dir: Optional[str], timeout: int = APIConfig.DEFAULT_TIMEOUT
) -> list:
    """Upload multiple files in batch and poll for ALL results."""
    if not file_paths:
        return []

    all_valid = True
    for fp in file_paths:
        issues = validate_file_for_api(fp)
        if issues:
            for issue in issues:
                print(f"  [Warning] {issue}")
            if any("exceeds" in i for i in issues):
                all_valid = False

    if not all_valid:
        raise MinerUError("Some files exceed API limits. Aborting batch.")

    headers = get_headers(token)

    model_versions = {determine_model_version(fp) for fp in file_paths}
    if len(model_versions) > 1:
        print(f"  [Warning] Mixed file types in batch require different models ({model_versions}). "
              f"Using '{list(model_versions)[0]}' for all.")
    model_version = list(model_versions)[0]

    files_data = []
    for fp in file_paths:
        filename = os.path.basename(fp)
        data_id = str(uuid.uuid4())[:8]
        file_entry = {"name": filename, "data_id": data_id}

        if "page_ranges" in optional_params:
            file_entry["page_ranges"] = optional_params["page_ranges"]
        if "is_ocr" in optional_params:
            file_entry["is_ocr"] = optional_params["is_ocr"]

        files_data.append(file_entry)

    payload = {"files": files_data, "model_version": model_version}
    payload.update({k: v for k, v in optional_params.items() if k in [
        "enable_formula", "enable_table", "language", "extra_formats"
    ]})

    print(f"\n[Batch Upload] Requesting upload URLs for {len(file_paths)} file(s)...")
    result = _check_response(
        make_request_with_retry("POST", APIConfig.API_V4_FILE_URLS_BATCH, headers=headers, json=payload),
        context="batch get upload URLs"
    )

    batch_id = result["data"]["batch_id"]
    upload_urls = result["data"]["file_urls"]

    if len(upload_urls) != len(file_paths):
        raise MinerUError(f"Got {len(upload_urls)} upload URLs for {len(file_paths)} files.")

    print(f"[Batch Upload] Batch ID: {batch_id}")

    for i, fp in enumerate(file_paths):
        filename = os.path.basename(fp)
        print(f"[Batch Upload] Uploading [{i+1}/{len(file_paths)}] {filename}...")
        with open(fp, "rb") as f:
            upload_response = make_request_with_retry("PUT", upload_urls[i], data=f)

        if upload_response.status_code != 200:
            msg = f"Upload failed for {filename}: HTTP {upload_response.status_code}"
            print(f"  [Error] {msg}")
            raise MinerUError(msg)
        size_mb = get_file_size_mb(fp)
        print(f"  OK ({size_mb:.1f}MB)")

    print(f"[Batch Upload] All files uploaded. Polling for results...")

    url = APIConfig.API_V4_EXTRACT_RESULTS_BATCH.format(batch_id=batch_id)
    start_time = time.time()

    while True:
        elapsed = time.time() - start_time
        if elapsed >= timeout:
            print(f"\nError: Batch polling timed out after {timeout} seconds.")
            raise MinerUError(f"Batch polling timed out after {timeout} seconds.")

        result = _check_response(
            make_request_with_retry("GET", url, headers=headers),
            context="batch poll"
        )
        data = result["data"]
        extract_results = data.get("extract_result", [])

        if len(extract_results) < len(file_paths):
            print(f"\r[{format_time(elapsed)}] Waiting for files ({len(extract_results)}/{len(file_paths)})...", end="", flush=True)
            time.sleep(APIConfig.POLL_INTERVAL)
            continue

        all_done = all(item.get("state") in ("done", "failed") for item in extract_results)
        done_count = sum(1 for item in extract_results if item.get("state") == "done")
        total = len(file_paths)

        print(f"\r[{format_time(elapsed)}] {done_count}/{total} completed...", end="", flush=True)

        if all_done:
            print()
            break

        time.sleep(APIConfig.POLL_INTERVAL)

    batch_results = []
    for item in extract_results:
        file_name = item.get("file_name", "unknown")
        original_path = next((fp for fp in file_paths if os.path.basename(fp) == file_name), file_name)

        if item.get("state") == "done":
            zip_url = item.get("full_zip_url")
            if zip_url:
                try:
                    md_content, name, od = download_and_extract(zip_url, token, file_name, output_dir=output_dir)
                    batch_results.append({
                        "status": "success", "file": original_path, "name": file_name,
                        "md": md_content, "output_dir": od
                    })
                    continue
                except Exception as e:
                    batch_results.append({
                        "status": "failed", "file": original_path, "name": file_name,
                        "error": f"Download failed: {e}"
                    })
                    continue
            batch_results.append({
                "status": "failed", "file": original_path, "name": file_name,
                "error": "Task done but no full_zip_url"
            })
        else:
            batch_results.append({
                "status": "failed", "file": original_path, "name": file_name,
                "error": item.get("err_msg", "Unknown error")
            })

    return batch_results


def process_batch(
    file_list: list, token: Optional[str], optional_params: dict,
    output_dir: Optional[str], is_url: bool = False, force_precision: bool = False,
    use_title_for_url: bool = False, no_save: bool = False, timestamp: bool = False,
    timeout: int = APIConfig.DEFAULT_TIMEOUT
) -> list:
    """Process multiple files or URLs in batch."""
    count_issues = validate_batch_count(len(file_list))
    for issue in count_issues:
        print(f"  [Warning] {issue}")
    if count_issues:
        file_list = file_list[:APIConfig.MAX_BATCH_FILES]

    results = []
    total = len(file_list)

    print(f"\n{'='*50}")
    print(f"Batch Processing: {total} item(s)")
    print(f"{'='*50}\n")

    if not is_url:
        file_list_str = ", ".join(os.path.basename(f) for f in file_list)
        print(f"  Files: {file_list_str}")

        try:
            if token is None:
                token = get_token()
            batch_results = _batch_upload_and_poll(file_list, token, optional_params, output_dir, timeout=timeout)
            for i, br in enumerate(batch_results, 1):
                original_filename = br["name"]
                output_path = generate_output_filename(original_filename, is_url=False)
                if output_dir:
                    output_path = os.path.join(output_dir, output_path)
                if timestamp:
                    output_path = _apply_timestamp(output_path)
                if br["status"] == "success":
                    print(f"[{i}/{total}] {original_filename}: OK")
                    if no_save:
                        print(f"\n{'='*50}")
                        print(f"--- {original_filename} ---")
                        print(f"{'='*50}")
                        print(br["md"])
                    else:
                        save_markdown(br["md"], output_path)
                    results.append({"status": "success", "input": br["file"], "output": output_path})
                else:
                    print(f"[{i}/{total}] {original_filename}: FAILED — {br['error']}")
                    results.append({"status": "failed", "input": br["file"], "error": br["error"]})
        except Exception as e:
            for fp in file_list:
                results.append({"status": "failed", "input": fp, "error": str(e)})

    if is_url:
        for i, item in enumerate(file_list, 1):
            print(f"\n[{i}/{total}] Processing: {item}")
            print("-" * 40)

            try:
                title = None
                if not force_precision and not _url_has_file_extension(item):
                    try:
                        md_content, original_filename, _ = lightweight_url_mode(
                            item, optional_params, output_dir=output_dir)
                    except MinerUError:
                        if token is None:
                            token = get_token()
                        md_content, original_filename, _ = url_mode(
                            item, token, optional_params, output_dir=output_dir, timeout=timeout)
                else:
                    if token is None:
                        token = get_token()
                    md_content, original_filename, _ = url_mode(
                        item, token, optional_params, output_dir=output_dir, timeout=timeout)

                if use_title_for_url and not _url_has_file_extension(item):
                    title = extract_title(md_content)
                    if title:
                        original_filename = title

                output_path = generate_output_filename(original_filename, is_url=not title)
                if output_dir:
                    output_path = os.path.join(output_dir, output_path)
                if timestamp:
                    output_path = _apply_timestamp(output_path)

                if no_save:
                    print(f"\n{'='*50}")
                    print(f"--- {original_filename} ---")
                    print(f"{'='*50}")
                    print(md_content)
                else:
                    save_markdown(md_content, output_path)

                results.append({"status": "success", "input": item, "output": output_path})

            except KeyboardInterrupt:
                print("\nInterrupted by user.")
                sys.exit(1)
            except Exception as e:
                print(f"Error processing {item}: {e}")
                results.append({"status": "failed", "input": item, "error": str(e)})

    print(f"\n{'='*50}")
    print(f"Batch Processing Summary")
    print(f"{'='*50}")
    success_count = sum(1 for r in results if r["status"] == "success")
    failed_count = sum(1 for r in results if r["status"] == "failed")
    print(f"Total: {total} | Success: {success_count} | Failed: {failed_count}")

    if failed_count > 0:
        print("\nFailed items:")
        for r in results:
            if r["status"] == "failed":
                print(f"  - {r['input']}: {r['error']}")

    return results


def show_help_languages():
    print("""
Available language codes:
  ch          - Chinese, English, Chinese Traditional (default)
  ch_server   - Chinese, English, Chinese Traditional, Japanese
  en          - English only
  japan       - Japanese focused
  korean      - Korean focused
  chinese_cht - Chinese Traditional focused
  ta          - Tamil
  te          - Telugu
  ka          - Kannada
  el          - Greek
  th          - Thai
  latin       - Latin script languages
  arabic      - Arabic script languages
  cyrillic    - Cyrillic script languages
    """)
    sys.exit(0)


# =============================================================================
# CLI Entry Point
# =============================================================================

def build_optional_params(args) -> dict:
    """Build optional parameters dictionary from command line arguments."""
    params = {}

    if args.enable_formula is not None:
        params["enable_formula"] = args.enable_formula
    if args.enable_table is not None:
        params["enable_table"] = args.enable_table
    if args.is_ocr is not None:
        params["is_ocr"] = args.is_ocr
    if args.language:
        params["language"] = args.language
    if args.page_ranges:
        params["page_ranges"] = args.page_ranges
    if args.extra_formats:
        params["extra_formats"] = args.extra_formats
    if args.no_cache:
        params["no_cache"] = args.no_cache
    if args.cache_tolerance is not None:
        params["cache_tolerance"] = args.cache_tolerance

    return params


def validate_args(args) -> None:
    """Validate CLI arguments. Raises MinerUError on invalid input."""
    if args.timeout is not None and args.timeout <= 0:
        raise MinerUError("--timeout must be a positive integer.")

    if args.output and os.path.exists(args.output) and not os.path.isdir(args.output):
        raise MinerUError(f"--output '{args.output}' is not a directory.")

    if args.page_ranges:
        page_ranges_pattern = re.compile(r'^\d+(-\d+)?(,\d+(-\d+)?)*$')
        if not page_ranges_pattern.match(args.page_ranges):
            raise MinerUError(
                f"--page-ranges format is invalid: '{args.page_ranges}'. "
                "Expected format: '1-10,15,20-25'"
            )

    if args.cache_tolerance is not None and args.cache_tolerance < 0:
        raise MinerUError("--cache-tolerance must be a non-negative integer.")


def main():
    if "--help-languages" in sys.argv:
        show_help_languages()

    if sys.platform == "win32":
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(
        description="Convert files or URLs to markdown using MinerU APIs.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python mineru2md.py --file ./document.pdf --output ./output/
  python mineru2md.py --url https://example.com/document.pdf --output ./output/
  python mineru2md.py --files file1.pdf file2.pdf --output ./results/
  python mineru2md.py --file ./doc.pdf --print
        """
    )

    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument("--file", "-f", help="Path to local file")
    input_group.add_argument("--files", "-F", nargs="+", help="Multiple local files")
    input_group.add_argument("--url", "-u", help="Remote URL to convert")
    input_group.add_argument("--urls", "-U", nargs="+", help="Multiple URLs")

    parser.add_argument("--output", "-o", help="Output directory (default: current directory)")

    parser.add_argument("--enable-formula", action="store_true", default=None)
    parser.add_argument("--disable-formula", dest="enable_formula", action="store_false", default=None)
    parser.add_argument("--enable-table", action="store_true", default=None)
    parser.add_argument("--disable-table", dest="enable_table", action="store_false", default=None)
    parser.add_argument("--is-ocr", action="store_true", default=None)
    parser.add_argument("--language", "-l", default="ch")
    parser.add_argument("--page-ranges", "-p", default=None)
    parser.add_argument("--extra-formats", nargs="+", choices=["docx", "html", "latex"])
    parser.add_argument("--no-cache", action="store_true")
    parser.add_argument("--cache-tolerance", type=int, default=None)
    parser.add_argument("--force-precision", action="store_true")
    parser.add_argument("--print", action="store_true")
    parser.add_argument("--timestamp", action="store_true")
    parser.add_argument("--timeout", type=int, default=APIConfig.DEFAULT_TIMEOUT)

    args = parser.parse_args()
    validate_args(args)
    optional_params = build_optional_params(args)
    token = None

    try:
        if args.files:
            expanded_files = []
            supported_globs = ("*.pdf", "*.png", "*.jpg", "*.jpeg", "*.jp2", "*.webp", "*.gif", "*.bmp",
                              "*.docx", "*.pptx", "*.xlsx", "*.doc", "*.ppt", "*.xls", "*.html", "*.htm")
            for f in args.files:
                if os.path.isdir(f):
                    found = []
                    for pattern in supported_globs:
                        found.extend(_glob.glob(os.path.join(f, pattern), recursive=False))
                        found.extend(_glob.glob(os.path.join(f, pattern.upper()), recursive=False))
                    if found:
                        expanded_files.extend(sorted(set(found)))
                    else:
                        print(f"  [Warning] No supported files found in directory: {f}")
                else:
                    expanded_files.append(f)
            args.files = expanded_files

            if not args.files:
                raise MinerUError("No supported files found.")

            process_batch(args.files, token, optional_params, args.output,
                          is_url=False, force_precision=args.force_precision,
                          use_title_for_url=False, no_save=args.print, timestamp=args.timestamp,
                          timeout=args.timeout)

        elif args.urls:
            process_batch(args.urls, None, optional_params, args.output, is_url=True,
                          use_title_for_url=True, no_save=args.print, timestamp=args.timestamp,
                          timeout=args.timeout)

        elif args.file:
            output_dir = args.output
            original_filename = generate_output_filename(args.file)
            if output_dir:
                output_path = os.path.join(output_dir, original_filename)
            else:
                output_path = original_filename
            if args.timestamp:
                output_path = _apply_timestamp(output_path)

            api_type, reason = get_routing_decision(args.file, args.force_precision)
            print(f"[Route] Using {'Precision' if api_type == 'precision' else 'Lightweight'} API ({reason})")

            if api_type == 'lightweight':
                md_content, _, _ = lightweight_file_mode(args.file, optional_params, output_dir=output_dir)
            else:
                token = get_token()
                md_content, _, _ = upload_file_mode(args.file, token, optional_params, output_dir=output_dir, timeout=args.timeout)

            if args.print:
                print(f"\n{'='*50}")
                print(f"--- {original_filename} ---")
                print(f"{'='*50}")
                print(md_content)
            else:
                save_markdown(md_content, output_path)
                print(f"\n{'='*50}")
                print(f"Conversion complete!")
                print(f"Output: {output_path}")
                print(f"{'='*50}")

        elif args.url:
            output_dir = args.output
            md_content, _, _ = parse_with_auto_routing(
                args.url, token=None, optional_params=optional_params,
                is_url=True, force_precision=args.force_precision,
                output_dir=output_dir, timeout=args.timeout)

            if not _url_has_file_extension(args.url):
                title = extract_title(md_content)
                if title:
                    original_filename = generate_output_filename(title)
                else:
                    original_filename = generate_output_filename(args.url, is_url=True)
            else:
                original_filename = generate_output_filename(args.url, is_url=True)

            if output_dir:
                output_path = os.path.join(output_dir, original_filename)
            else:
                output_path = original_filename

            if args.timestamp:
                output_path = _apply_timestamp(output_path)

            if args.print:
                print(f"\n{'='*50}")
                print(f"--- {original_filename} ---")
                print(f"{'='*50}")
                print(md_content)
            else:
                save_markdown(md_content, output_path)
                print(f"\n{'='*50}")
                print(f"Conversion complete!")
                print(f"Output: {output_path}")
                print(f"{'='*50}")

    except KeyboardInterrupt:
        print("\nInterrupted by user.")
        sys.exit(1)
    except MinerUError as e:
        print(f"Error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
