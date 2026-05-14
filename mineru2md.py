#!/usr/bin/env python3
"""
MinerU Converter - Convert files or URLs to markdown using MinerU APIs.

Auto-routes between Lightweight Agent API (no token needed) and Precision API (token needed)
based on file characteristics.

Lightweight API (auto-selected when file qualifies):
  - File size ≤ 10 MB, page count ≤ 20, supported type (PDF, image, Docx, PPTx, Xlsx)
  - No token required

Precision API (fallback):
  - Files >10 MB, >20 pages, or unsupported types
  - Token required (MINERU_TOKEN)

Usage:
    python mineru2md.py --file <path>           # File upload mode (auto-routed)
    python mineru2md.py --url <url>             # URL mode (auto-routed for articles)
    python mineru2md.py --file <path> --output <output.md>

    # Batch mode (multiple files/URLs)
    python mineru2md.py --files file1.pdf file2.pdf --output-dir ./results
    python mineru2md.py --urls url1.pdf url2.pdf --output-dir ./results

    # With optional parameters
    python mineru2md.py --file ./doc.pdf --enable-formula --enable-table --language en
    python mineru2md.py --url https://example.com/doc.pdf --page-ranges 1-10,20

    # Force Precision API for compatible files
    python mineru2md.py --file ./doc.pdf --force-precision

    # Print to stdout instead of saving
    python mineru2md.py --file ./doc.pdf --print
    python mineru2md.py --url https://example.com/article --print

    # Add timestamp to output filename
    python mineru2md.py --url https://example.com/article --timestamp

Environment:
    MINERU_TOKEN - API token for authentication (Bearer token). Only needed for Precision API.
                   Article URLs try Lightweight API first (no token), fallback to Precision.
"""

import argparse
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

import requests


class MinerUError(Exception):
    """Base exception for MinerU errors."""
    pass


# API Configuration
BASE_URL = "https://mineru.net"
API_V4_FILE_URLS_BATCH = f"{BASE_URL}/api/v4/file-urls/batch"
API_V4_EXTRACT_TASK_BATCH = f"{BASE_URL}/api/v4/extract/task/batch"
API_V4_EXTRACT_TASK = f"{BASE_URL}/api/v4/extract/task"
API_V4_EXTRACT_TASK_ID = f"{BASE_URL}/api/v4/extract/task/{{task_id}}"
API_V4_EXTRACT_RESULTS_BATCH = f"{BASE_URL}/api/v4/extract-results/batch/{{batch_id}}"

# Polling configuration
POLL_INTERVAL = 3  # seconds
DEFAULT_TIMEOUT = 300  # seconds
MAX_RETRIES = 3
INITIAL_BACKOFF = 1  # seconds


# Lightweight Agent API Configuration (no token needed)
AGENT_API_BASE = "https://mineru.net/api/v1/agent"
AGENT_PARSE_URL = f"{AGENT_API_BASE}/parse/url"
AGENT_PARSE_FILE = f"{AGENT_API_BASE}/parse/file"
AGENT_QUERY_RESULT = f"{AGENT_API_BASE}/parse/{{task_id}}"

# Lightweight API polling
AGENT_POLL_INTERVAL = 2  # seconds
AGENT_DEFAULT_TIMEOUT = 180  # seconds

# Lightweight API error codes
AGENT_ERROR_CODES = {
    "-30001": ("File too large for lightweight API", "File exceeds 10MB limit. Use precision API."),
    "-30002": ("Unsupported file type for lightweight API", "Use PDF/image/Docx/PPTx/Xlsx for lightweight API."),
    "-30003": ("Page count exceeds lightweight API limit", "File exceeds 20 page limit. Use precision API or specify page_range."),
    "-30004": ("Request parameter error", "Check required parameters."),
}

# Lightweight API supported file extensions
LIGHTWEIGHT_SUPPORTED_EXTENSIONS = {"pdf", "png", "jpg", "jpeg", "jp2", "webp", "gif", "bmp", "docx", "pptx", "xlsx"}

# Error code mappings for user-friendly messages
ERROR_CODES = {
    "A0202": ("Token error", "Check that your MINERU_TOKEN is correct. Ensure it has 'Bearer ' prefix."),
    "A0211": ("Token expired", "Your token has expired. Please obtain a new token from the MinerU dashboard."),
    "-500": ("Parameter error", "Ensure parameter types and Content-Type are correct."),
    "-10001": ("Service error", "The service is temporarily unavailable. Please try again later."),
    "-10002": ("Request parameter error", "Check your request parameters format."),
    "-60001": ("Upload URL generation failed", "Please try again later."),
    "-60002": ("File format matching failed", "Ensure filename has correct extension (pdf, doc, docx, ppt, pptx, xls, xlsx, png, jp(e)g)."),
    "-60003": ("File read failed", "The file may be corrupted. Please check and re-upload."),
    "-60004": ("Empty file", "Please upload a valid non-empty file."),
    "-60005": ("File size exceeds limit", "Maximum file size is 200MB."),
    "-60006": ("Page count exceeds limit", "Maximum page count is 200. Please split the file."),
    "-60007": ("Model service temporarily unavailable", "Please try again later or contact support."),
    "-60008": ("File read timeout", "Check that the URL is accessible and try again."),
    "-60009": ("Task queue full", "Please try again later."),
    "-60010": ("Parsing failed", "Please try again."),
    "-60011": ("Invalid file", "Ensure the file has been uploaded successfully."),
    "-60012": ("Task not found", "Verify the task_id is valid and has not been deleted."),
    "-60013": ("Access denied", "You can only access your own tasks."),
    "-60014": ("Cannot delete running task", "Running tasks cannot be deleted."),
    "-60015": ("File conversion failed", "Try converting to PDF manually and re-upload."),
    "-60016": ("File conversion failed", "Try a different export format or retry."),
    "-60017": ("Retry limit reached", "Wait for model upgrade and retry."),
    "-60018": ("Daily limit reached", "Daily parsing limit reached. Try again tomorrow."),
    "-60019": ("HTML parsing quota exceeded", "HTML parsing quota exceeded. Try again tomorrow."),
    "-60020": ("File splitting failed", "Please try again later."),
    "-60021": ("Page count reading failed", "Please try again later."),
    "-60022": ("Webpage read failed", "Failed to read the webpage. May be due to network issues or rate limiting."),
}


def get_token():
    """Get API token from environment variable."""
    token = os.environ.get("MINERU_TOKEN")
    if not token:
        raise MinerUError("MINERU_TOKEN environment variable is not set.")
    return token


def get_headers(token):
    """Get headers with authorization."""
    return {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}"
    }


def extract_file_extension(filename):
    """Extract file extension from filename."""
    if "." in filename:
        return filename.rsplit(".", 1)[1].lower()
    return ""


def determine_model_version(filename_or_url, is_url=False):
    """
    Determine model version based on file extension or URL.

    For HTML files or URLs pointing to web pages (no downloadable file extension
    or .html/.htm extension), use MinerU-HTML. For PDFs, documents, images, use vlm.
    """
    if is_url:
        if _url_has_file_extension(filename_or_url):
            return "vlm"
        # URL has no downloadable extension, or is .html/.htm → MinerU-HTML
        return "MinerU-HTML"
    else:
        ext = extract_file_extension(filename_or_url)
        html_extensions = {"html", "htm"}
        if ext in html_extensions:
            return "MinerU-HTML"
        return "vlm"


def parse_error_response(result):
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


def get_file_size_mb(file_path):
    """Get file size in MB."""
    size_bytes = os.path.getsize(file_path)
    return size_bytes / (1024 * 1024)


def get_page_count(file_path):
    """
    Get page count for PDF files using PyMuPDF (fitz).

    Returns:
        int: Page count (0 for non-PDF files)
        None: If PyMuPDF is not available or page count cannot be determined
    """
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
        print("  [Warning] PyMuPDF (fitz) not available. Cannot check page count.")
        return None
    except Exception as e:
        print(f"  [Warning] Failed to get page count: {e}")
        return None


def is_supported_lightweight_type(file_path):
    """Check if file extension is supported by the Lightweight Agent API."""
    ext = extract_file_extension(file_path)
    return ext in LIGHTWEIGHT_SUPPORTED_EXTENSIONS


def is_lightweight_compatible(file_path):
    """
    Check if file qualifies for the Lightweight Agent API.

    Conditions (all must be met):
    - File extension must be in LIGHTWEIGHT_SUPPORTED_EXTENSIONS
    - File size must be ≤ 10 MB
    - Page count must be ≤ 20 (for PDFs; non-PDFs have page count 0)
    - PyMuPDF must be available for PDFs (otherwise cannot verify page count)

    Returns:
        bool: True if file is compatible with lightweight API
    """
    if not is_supported_lightweight_type(file_path):
        return False

    size_mb = get_file_size_mb(file_path)
    if size_mb > 10:
        return False

    pages = get_page_count(file_path)
    if pages is None:
        # Cannot determine page count for PDF - fall back to precision API
        return False
    if pages > 20:
        return False

    return True


def get_routing_decision(file_path, force_precision=False):
    """
    Determine which API to use and return (api_type, reason).

    Returns:
        tuple: (api_type: 'lightweight'|'precision', reason: str)
    """
    if force_precision:
        return 'precision', "forced via --force-precision"

    if is_lightweight_compatible(file_path):
        return 'lightweight', "no token needed"

    reasons = []
    if not is_supported_lightweight_type(file_path):
        reasons.append("unsupported file type")
    size_mb = get_file_size_mb(file_path)
    if size_mb > 10:
        reasons.append(f"file size {size_mb:.1f}MB > 10MB")
    pages = get_page_count(file_path)
    if pages is not None and pages > 20:
        reasons.append(f"page count {pages} > 20")
    elif pages is None:
        reasons.append("cannot determine page count")

    reason_str = "; ".join(reasons) if reasons else "default"
    return 'precision', reason_str


def make_request_with_retry(method, url, headers=None, json=None, data=None,
                             max_retries=MAX_RETRIES, backoff=INITIAL_BACKOFF):
    """
    Make HTTP request with retry logic and exponential backoff.
    """
    last_exception = None

    for attempt in range(max_retries + 1):
        try:
            if method.upper() == "GET":
                response = requests.get(url, headers=headers, json=json, timeout=60)
            elif method.upper() == "POST":
                response = requests.post(url, headers=headers, json=json, data=data, timeout=60)
            elif method.upper() == "PUT":
                response = requests.put(url, headers=headers, data=data, timeout=120)
            else:
                response = requests.request(method, url, headers=headers, json=json, data=data, timeout=60)

            # Don't retry on client errors (4xx) except 429 (rate limit) and 5xx
            if 400 <= response.status_code < 500 and response.status_code != 429:
                return response

            # Retry on 5xx errors or rate limiting
            if response.status_code >= 500 or response.status_code == 429:
                if attempt < max_retries:
                    wait_time = backoff * (2 ** attempt)
                    print(f"  Request failed with status {response.status_code}. Retrying in {wait_time}s... (attempt {attempt + 1}/{max_retries})")
                    time.sleep(wait_time)
                    continue

            return response

        except requests.exceptions.Timeout as e:
            last_exception = e
            if attempt < max_retries:
                wait_time = backoff * (2 ** attempt)
                print(f"  Request timed out. Retrying in {wait_time}s... (attempt {attempt + 1}/{max_retries})")
                time.sleep(wait_time)
        except requests.exceptions.RequestException as e:
            last_exception = e
            if attempt < max_retries:
                wait_time = backoff * (2 ** attempt)
                print(f"  Request failed: {e}. Retrying in {wait_time}s... (attempt {attempt + 1}/{max_retries})")
                time.sleep(wait_time)

    print(f"  All {max_retries + 1} attempts failed.")
    if last_exception:
        raise last_exception
    return response


def build_optional_params(args):
    """Build optional parameters dictionary from command line arguments."""
    params = {}

    if hasattr(args, 'enable_formula') and args.enable_formula is not None:
        params["enable_formula"] = args.enable_formula

    if hasattr(args, 'enable_table') and args.enable_table is not None:
        params["enable_table"] = args.enable_table

    if hasattr(args, 'is_ocr') and args.is_ocr is not None:
        params["is_ocr"] = args.is_ocr

    if hasattr(args, 'language') and args.language:
        params["language"] = args.language

    if hasattr(args, 'page_ranges') and args.page_ranges:
        params["page_ranges"] = args.page_ranges

    if hasattr(args, 'extra_formats') and args.extra_formats:
        params["extra_formats"] = args.extra_formats

    if hasattr(args, 'no_cache') and args.no_cache:
        params["no_cache"] = args.no_cache

    if hasattr(args, 'cache_tolerance') and args.cache_tolerance is not None:
        params["cache_tolerance"] = args.cache_tolerance

    return params


def upload_file_mode(file_path, token, optional_params, output_dir=None):
    """
    Handle file upload mode.
    1. Get upload URLs via POST /api/v4/file-urls/batch
    2. Upload file via PUT to the upload URL
    3. Poll for results via GET /api/v4/extract-results/batch/{batch_id}
    4. Download zip, extract full.md, save it
    """
    filename = os.path.basename(file_path)
    data_id = str(uuid.uuid4())[:8]

    print(f"[File Mode] Processing: {filename}")
    print(f"[File Mode] Data ID: {data_id}")

    # Determine model version
    model_version = determine_model_version(filename)
    print(f"[File Mode] Model version: {model_version}")

    # Build request payload with optional parameters
    payload = {
        "files": [{"name": filename, "data_id": data_id}],
        "model_version": model_version
    }
    payload.update({k: v for k, v in optional_params.items() if k in [
        "enable_formula", "enable_table", "language", "extra_formats"
    ]})

    # Add file-level optional params
    if "page_ranges" in optional_params:
        payload["files"][0]["page_ranges"] = optional_params["page_ranges"]
    if "is_ocr" in optional_params:
        payload["files"][0]["is_ocr"] = optional_params["is_ocr"]

    # Step 1: Get upload URL
    headers = get_headers(token)
    print(f"[File Mode] Requesting upload URL...")
    response = make_request_with_retry("POST", API_V4_FILE_URLS_BATCH, headers=headers, json=payload)

    if response.status_code != 200:
        print(f"Error: Failed to get upload URL. Status: {response.status_code}")
        print(f"Response: {response.text}")
        raise MinerUError(f"Failed to get upload URL. Status: {response.status_code}")

    result = response.json()
    if result.get("code") != 0:
        print(parse_error_response(result))
        raise MinerUError(parse_error_response(result))

    batch_id = result["data"]["batch_id"]
    upload_url = result["data"]["file_urls"][0]
    print(f"[File Mode] Got upload URL. Batch ID: {batch_id}")

    # Step 2: Upload file
    print(f"[File Mode] Uploading file...")
    with open(file_path, "rb") as f:
        upload_response = make_request_with_retry("PUT", upload_url, data=f)

    if upload_response.status_code != 200:
        print(f"Error: Failed to upload file. Status: {upload_response.status_code}")
        print(f"Response: {upload_response.text}")
        raise MinerUError(f"Failed to upload file. Status: {upload_response.status_code}")

    print(f"[File Mode] File uploaded successfully.")

    # Step 3: Poll for results
    return poll_batch_results(batch_id, token, filename, output_dir=output_dir)


def submit_url_task(url, token, optional_params):
    """
    Submit URL for extraction via POST /api/v4/extract/task/batch.
    Returns batch_id.
    """
    headers = get_headers(token)
    data_id = str(uuid.uuid4())[:8]

    # Determine model version from URL
    model_version = determine_model_version(url, is_url=True)

    # Build request payload
    payload = {
        "files": [{"url": url, "data_id": data_id}],
        "model_version": model_version
    }
    payload.update({k: v for k, v in optional_params.items() if k in [
        "enable_formula", "enable_table", "language", "extra_formats", "no_cache", "cache_tolerance"
    ]})

    response = make_request_with_retry("POST", API_V4_EXTRACT_TASK_BATCH, headers=headers, json=payload)

    if response.status_code != 200:
        print(f"Error: Failed to submit URL. Status: {response.status_code}")
        print(f"Response: {response.text}")
        raise MinerUError(f"Failed to submit URL. Status: {response.status_code}")

    result = response.json()
    if result.get("code") != 0:
        print(parse_error_response(result))
        raise MinerUError(parse_error_response(result))

    batch_id = result["data"]["batch_id"]
    return batch_id


def url_mode(url, token, optional_params, output_dir=None):
    """
    Handle URL mode.
    1. Submit URL via POST /api/v4/extract/task/batch
    2. Poll for results via GET /api/v4/extract-results/batch/{batch_id}
    3. Download zip, extract full.md, save it
    """
    print(f"[URL Mode] Processing: {url}")

    # Submit URL task
    batch_id = submit_url_task(url, token, optional_params)
    print(f"[URL Mode] Batch ID: {batch_id}")

    # Poll for results
    filename = url.split("/")[-1].split("?")[0] if "/" in url else url
    return poll_batch_results(batch_id, token, filename, output_dir=output_dir)


def poll_task_results(task_id, token, filename, timeout=DEFAULT_TIMEOUT, output_dir=None):
    """
    Poll for single task results (used for direct file POST).
    """
    headers = get_headers(token)
    url = API_V4_EXTRACT_TASK_ID.format(task_id=task_id)

    print(f"[Task Mode] Polling task: {task_id}")
    return poll_with_progress(url, headers, timeout, filename, token, output_dir=output_dir,
                              extract_key="task_id")


def poll_batch_results(batch_id, token, filename, timeout=DEFAULT_TIMEOUT, output_dir=None):
    """
    Poll for batch results.
    """
    headers = get_headers(token)
    url = API_V4_EXTRACT_RESULTS_BATCH.format(batch_id=batch_id)

    print(f"[Batch Mode] Polling batch: {batch_id}")
    return poll_with_progress(url, headers, timeout, filename, token, output_dir=output_dir,
                              extract_key="batch_id")


def poll_with_progress(url, headers, timeout, filename, token, output_dir=None, extract_key="task_id"):
    """
    Poll for results with progress bar and timeout handling.
    """
    start_time = time.time()
    last_state = None
    last_progress_update = 0

    while True:
        # Check timeout
        elapsed = time.time() - start_time
        if elapsed >= timeout:
            print(f"\nError: Polling timed out after {timeout} seconds.")
            print(f"You can check the task status later using the batch/task ID.")
            raise MinerUError(f"Polling timed out after {timeout} seconds.")

        # Make request
        response = requests.get(url, headers=headers)

        if response.status_code != 200:
            print(f"\nError: Failed to query status. Status: {response.status_code}")
            print(f"Response: {response.text}")
            raise MinerUError(f"Failed to query status. Status: {response.status_code}")

        result = response.json()
        if result.get("code") != 0:
            print(f"\n{parse_error_response(result)}")
            raise MinerUError(parse_error_response(result))

        data = result["data"]

        # Handle batch results
        if "extract_result" in data:
            extract_results = data.get("extract_result", [])
            if not extract_results:
                print(f"\r[{format_time(elapsed)}] Waiting for results... ", end="", flush=True)
                time.sleep(POLL_INTERVAL)
                continue

            file_result = extract_results[0]
            state = file_result.get("state")
            file_name = file_result.get("file_name", filename)

            # Update progress display
            if state != last_state or elapsed - last_progress_update >= 5:
                update_progress(state, elapsed, file_result, data)
                last_state = state
                last_progress_update = elapsed

            if state == "done":
                full_zip_url = file_result.get("full_zip_url")
                if full_zip_url:
                    return download_and_extract(full_zip_url, token, file_name, output_dir=output_dir)
                else:
                    print("\nError: Task done but no full_zip_url returned.")
                    raise MinerUError("Task done but no full_zip_url returned.")
            elif state == "failed":
                print(f"\nError: Task failed. Reason: {file_result.get('err_msg')}")
                raise MinerUError(f"Task failed. Reason: {file_result.get('err_msg')}")
            elif state in ("pending", "running", "converting", "waiting-file"):
                print(f"\r[{format_time(elapsed)}] {state.capitalize()}... ", end="", flush=True)
                time.sleep(POLL_INTERVAL)
            else:
                print(f"\nUnknown state: {state}")
                time.sleep(POLL_INTERVAL)
        else:
            # Handle single task result
            state = data.get("state")

            if state == "done":
                full_zip_url = data.get("full_zip_url")
                if full_zip_url:
                    return download_and_extract(full_zip_url, token, filename, output_dir=output_dir)
                else:
                    print("\nError: Task done but no full_zip_url returned.")
                    raise MinerUError("Task done but no full_zip_url returned.")
            elif state == "failed":
                print(f"\nError: Task failed. Reason: {data.get('err_msg')}")
                raise MinerUError(f"Task failed. Reason: {data.get('err_msg')}")
            elif state in ("pending", "running", "converting"):
                update_progress(state, elapsed, data, data)
                time.sleep(POLL_INTERVAL)
            else:
                print(f"\nUnknown state: {state}")
                time.sleep(POLL_INTERVAL)


def update_progress(state, elapsed, file_result, data):
    """Update progress display."""
    progress_str = f"\r[{format_time(elapsed)}] {state.capitalize()}"

    if state == "running" and "extract_progress" in file_result:
        progress = file_result["extract_progress"]
        extracted = progress.get('extracted_pages', 0)
        total = progress.get('total_pages', '?')
        progress_str += f" - Extracted {extracted}/{total} pages"
    elif state == "running" and "extract_progress" in data:
        progress = data["extract_progress"]
        extracted = progress.get('extracted_pages', 0)
        total = progress.get('total_pages', '?')
        progress_str += f" - Extracted {extracted}/{total} pages"

    print(progress_str + " " * 10, end="", flush=True)


def format_time(seconds):
    """Format seconds to mm:ss."""
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{minutes:02d}:{secs:02d}"


def download_and_extract(zip_url, token, original_filename, output_dir=None):
    """
    Download zip file, extract full.md and images/ folder, save them.

    Uses streaming download to temp file to avoid memory issues with large zips.
    Rewrites image references in markdown to point to local images directory.
    """
    print(f"\n[Download] Downloading result from: {zip_url}")

    # Download the zip file (streaming to temp file)
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    tmp_path = None
    try:
        # Stream download to temp file (write inside the NamedTemporaryFile context)
        with tempfile.NamedTemporaryFile(delete=False, suffix='.zip') as tmp:
            tmp_path = tmp.name
            with requests.get(zip_url, headers=headers, timeout=120, stream=True) as response:
                if response.status_code != 200:
                    print(f"Error: Failed to download zip. Status: {response.status_code}")
                    raise MinerUError(f"Failed to download zip. Status: {response.status_code}")

                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        tmp.write(chunk)

        print(f"[Download] Downloaded to temp file: {tmp_path}")

        # Extract full.md and images/ folder from zip
        with zipfile.ZipFile(tmp_path) as zf:
            # List files in zip for debugging
            file_list = zf.namelist()
            print(f"[Extract] Zip contains {len(file_list)} files: {file_list}")

            # Find full.md
            full_md_name = None
            for name in file_list:
                if name.lower() == "full.md":
                    full_md_name = name
                    break

            if not full_md_name:
                print(f"Error: full.md not found in zip. Files: {file_list}")
                raise MinerUError("full.md not found in zip")

            # Read full.md content
            with zf.open(full_md_name) as md_file:
                md_content = md_file.read().decode("utf-8")

            print(f"[Extract] Extracted full.md ({len(md_content)} bytes)")

            # Extract images/ folder if present
            images_dir = None
            for name in file_list:
                if name.startswith("images/") or name.startswith("images\\"):
                    if images_dir is None:
                        # Determine output directory for images
                        if output_dir:
                            images_dir = os.path.join(output_dir, "images")
                        else:
                            images_dir = os.path.join(os.path.dirname(original_filename) or ".", "images")
                        os.makedirs(images_dir, exist_ok=True)
                        print(f"[Extract] Extracting images to: {images_dir}")

                    # Extract image file
                    img_data = zf.read(name)
                    # Handle both forward slash and backslash paths
                    img_filename = os.path.basename(name.replace("\\", "/"))
                    img_path = os.path.join(images_dir, img_filename)
                    with open(img_path, "wb") as img_file:
                        img_file.write(img_data)

            if images_dir:
                image_count = len([n for n in file_list if n.startswith("images/") or n.startswith("images\\")])
                print(f"[Extract] Extracted {image_count} image(s)")

                # Rewrite image references in markdown to point to local images directory
                if output_dir:
                    rel_images_path = os.path.relpath(images_dir, output_dir)
                else:
                    md_dir = os.path.dirname(original_filename) if os.path.dirname(original_filename) else "."
                    rel_images_path = os.path.relpath(images_dir, md_dir)

                # Replace image references like ![...](images/xxx) or ![...](./images/xxx)
                md_content = re.sub(
                    r'!\[([^\]]*)\]\((images/[^\)]+)\)',
                    f'![\\1]({rel_images_path}/\\2)',
                    md_content
                )
                # Also handle markdown that references images/ without the prefix
                md_content = re.sub(
                    r'!\[([^\]]*)\]\(\./(images/[^\)]+)\)',
                    f'![\\1]({rel_images_path}/\\2)',
                    md_content
                )

            return md_content, original_filename, output_dir

    except zipfile.BadZipFile:
        print("Error: Downloaded file is not a valid zip file.")
        print(f"Content (first 500 chars): {response.content[:500]}")
        raise MinerUError("Downloaded file is not a valid zip file.")
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


# =============================================================================
# Lightweight Agent API Functions (no token required)
# =============================================================================


def lightweight_parse_by_file(file_path, **kwargs):
    """
    Submit a local file to the Lightweight Agent API for parsing.

    Uses signature upload mode:
    1. POST JSON with file_name to get task_id and signed upload URL
    2. PUT file content to the signed URL

    No token required.

    Args:
        file_path: Path to the local file
        **kwargs: Additional parameters (page_range, enable_formula, etc.)

    Returns:
        str: task_id for polling
    """
    filename = os.path.basename(file_path)

    # Step 1: Get signed upload URL
    payload = {"file_name": filename}
    if kwargs:
        payload.update(kwargs)

    print(f"[Lightweight API] Submitting file: {filename}")
    response = requests.post(AGENT_PARSE_FILE, json=payload, timeout=60)

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

    # Step 2: PUT file to signed URL
    print(f"[Lightweight API] Uploading file to OSS...")
    with open(file_path, "rb") as f:
        upload_response = requests.put(file_url, data=f, timeout=120)

    if upload_response.status_code not in (200, 201):
        print(f"Error: File upload failed. Status: {upload_response.status_code}")
        print(f"Response: {upload_response.text}")
        raise MinerUError(f"File upload failed. Status: {upload_response.status_code}")

    print(f"[Lightweight API] File uploaded successfully.")
    return task_id


def lightweight_parse_by_url(url, **kwargs):
    """
    Submit a URL to the Lightweight Agent API for parsing.

    No token required.

    Args:
        url: Remote URL to parse
        **kwargs: Additional parameters (enable_formula, enable_table, etc.)

    Returns:
        str: task_id for polling
    """
    payload = {"url": url}
    if kwargs:
        payload.update(kwargs)

    print(f"[Lightweight API] Submitting URL: {url}")
    response = requests.post(AGENT_PARSE_URL, json=payload, timeout=60)

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


def lightweight_poll_result(task_id, timeout=AGENT_DEFAULT_TIMEOUT):
    """
    Poll the Lightweight Agent API for parsing results.

    Args:
        task_id: Task ID from lightweight_parse_by_file or lightweight_parse_by_url
        timeout: Maximum polling time in seconds (default: 180)

    Returns:
        str: Markdown content
    """
    url = AGENT_QUERY_RESULT.format(task_id=task_id)
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
            response = requests.get(url, timeout=60)
        except requests.exceptions.RequestException as e:
            print(f"\nError: Request failed: {e}")
            time.sleep(AGENT_POLL_INTERVAL)
            continue

        if response.status_code == 429:
            # Rate limited - wait and retry
            wait = AGENT_POLL_INTERVAL * 2
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

        # Update progress display
        if state != last_state or elapsed - last_progress_update >= 5:
            if state:
                print(f"\r[{format_time(elapsed)}] Lightweight: {state.capitalize()}... ", end="", flush=True)
            else:
                print(f"\r[{format_time(elapsed)}] Waiting... ", end="", flush=True)
            last_state = state
            last_progress_update = elapsed

        if state == "done":
            print(f"\r[{format_time(elapsed)}] Done!                              ")
            # Get markdown content from markdown_url
            markdown_url = data.get("markdown_url")
            if markdown_url:
                md_response = requests.get(markdown_url, timeout=60)
                if md_response.status_code == 200:
                    return md_response.text
                else:
                    print(f"\nError: Failed to download markdown from {markdown_url}, status: {md_response.status_code}")
                    raise MinerUError(f"Failed to download markdown from {markdown_url}")
            # Fallback: try direct markdown fields
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
        elif state in ("pending", "running", "converting", "waiting-file"):
            time.sleep(AGENT_POLL_INTERVAL)
        else:
            if state:
                print(f"\nUnknown state: {state}")
            time.sleep(AGENT_POLL_INTERVAL)


def lightweight_file_mode(file_path, optional_params, output_dir=None):
    """
    Handle lightweight API file mode end-to-end: upload, poll, return markdown.

    Returns:
        tuple: (markdown_content, original_filename, output_dir)
    """
    task_id = lightweight_parse_by_file(file_path, **optional_params)
    md_content = lightweight_poll_result(task_id)
    filename = os.path.basename(file_path)
    return md_content, filename, output_dir


def lightweight_url_mode(url, optional_params, output_dir=None):
    """
    Handle lightweight API URL mode end-to-end: submit, poll, return markdown.

    Returns:
        tuple: (markdown_content, original_filename, output_dir)
    """
    task_id = lightweight_parse_by_url(url, **optional_params)
    md_content = lightweight_poll_result(task_id)
    filename = url.split("/")[-1].split("?")[0]
    return md_content, filename, output_dir


def parse_with_auto_routing(file_path_or_url, token, optional_params,
                            is_url=False, force_precision=False, output_dir=None):
    """
    Main routing function that automatically selects between Lightweight Agent API
    and Precision API based on file characteristics.

    Lightweight API (no token needed):
      - File size ≤ 10 MB AND page count ≤ 20 AND supported type

    Precision API (token needed):
      - File size > 10 MB OR page count > 20 OR unsupported type OR URL mode

    Args:
        file_path_or_url: Path to local file or remote URL
        token: MinerU API token (can be None if lightweight API is used)
        optional_params: Dict of optional parameters
        is_url: Whether the input is a URL
        force_precision: Force use of Precision API
        output_dir: Output directory for results

    Returns:
        tuple: (markdown_content, original_filename, output_dir)
    """
    if is_url:
        # URLs: direct file URLs (pdf, png, etc.) → Precision API only
        # Article URLs (no file extension, or .html/.htm) → try Lightweight API first, fallback Precision
        if force_precision or _url_has_file_extension(file_path_or_url):
            print(f"[Route] Using Precision API (URL mode)")
            return url_mode(file_path_or_url, token, optional_params, output_dir=output_dir)
        else:
            print(f"[Route] Attempting Lightweight API for article URL...")
            try:
                result = lightweight_url_mode(file_path_or_url, optional_params, output_dir=output_dir)
                print(f"[Route] Lightweight API succeeded")
                return result
            except MinerUError as e:
                print(f"[Route] Lightweight API failed: {e}")
                print(f"[Route] Falling back to Precision API...")
                if token is None:
                    token = get_token()
                return url_mode(file_path_or_url, token, optional_params, output_dir=output_dir)

    # File mode - use routing decision helper
    api_type, reason = get_routing_decision(file_path_or_url, force_precision)
    print(f"[Route] Using {'Precision' if api_type == 'precision' else 'Lightweight'} API ({reason})")

    if api_type == 'lightweight':
        return lightweight_file_mode(file_path_or_url, optional_params, output_dir=output_dir)
    else:
        return upload_file_mode(file_path_or_url, token, optional_params, output_dir=output_dir)


def extract_title(md_content):
    """
    Extract the first level-1 heading (# ) from markdown content to use as filename.

    Returns:
        str or None: Sanitized title suitable for use as filename, or None if no heading found.
    """
    match = re.search(r'^#\s+(.+)$', md_content, re.MULTILINE)
    if match:
        title = match.group(1).strip()
        # Remove or replace characters invalid in filenames
        title = re.sub(r'[\\/:*?"<>|]', '_', title)
        # Remove leading/trailing whitespace and dots
        title = title.strip().strip('.')
        # Truncate to reasonable length
        if len(title) > 100:
            title = title[:100].rstrip()
        if not title:
            return None
        return title
    return None


def _url_has_file_extension(url):
    """Check if URL path ends with a recognizable file extension.

    URLs pointing to downloadable documents (PDF, images, Office docs) should
    keep the URL-derived filename. URLs pointing to web articles or .html/.htm
    pages should use the document title instead.
    """
    parsed = urlparse(url)
    path = parsed.path.rstrip("/")
    last_seg = path.split("/")[-1] if "/" in path else ""
    ext_match = re.search(r'\.([a-zA-Z]{2,5})$', last_seg)
    if not ext_match:
        return False
    ext = ext_match.group(1).lower()
    # .html/.htm pages are web articles, not direct file downloads
    download_extensions = {"pdf", "png", "jpg", "jpeg", "jp2", "webp", "gif", "bmp",
                           "docx", "pptx", "xlsx", "doc", "ppt", "xls"}
    return ext in download_extensions


def _apply_timestamp(output_path):
    """Prepend current date (YYYY-MM-DD) to the output filename."""
    date_prefix = datetime.now().strftime("%Y-%m-%d ")
    parent = os.path.dirname(output_path)
    basename = os.path.basename(output_path)
    new_name = date_prefix + basename
    if parent:
        return os.path.join(parent, new_name)
    return new_name


def save_markdown(content, output_path):
    """Save markdown content to file."""
    # Ensure output directory exists
    output_dir = os.path.dirname(output_path)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"[Save] Markdown saved to: {output_path}")


def generate_output_filename(input_path, is_url=False, output_dir=None):
    """Generate output filename from input path or URL."""
    if is_url:
        # For URL, extract filename from URL
        url_part = input_path.split("/")[-1].split("?")[0]
        if "." in url_part:
            filename = url_part.rsplit(".", 1)[0] + ".md"
        else:
            filename = url_part + ".md"
    else:
        # For file path or title, use the base name
        basename = os.path.basename(input_path)
        if "." in basename:
            name_part, _, ext = basename.rpartition(".")
            # Only strip if the last part looks like a file extension (alphabetic, 2-5 chars)
            if re.match(r'^[a-zA-Z]{2,5}$', ext):
                filename = name_part + ".md"
            else:
                filename = basename + ".md"
        else:
            filename = basename + ".md"

    if output_dir:
        return os.path.join(output_dir, filename)
    return filename


def process_batch(file_list, token, optional_params, output_dir, is_url=False, force_precision=False,
                  use_title_for_url=False, no_save=False, timestamp=False):
    """
    Process multiple files or URLs in batch.

    For files, each item is auto-routed to Lightweight or Precision API
    based on file characteristics. Article URLs try Lightweight API first,
    falling back to Precision API. File URLs use Precision API directly.
    """
    results = []
    total = len(file_list)

    print(f"\n{'='*50}")
    print(f"Batch Processing: {total} item(s)")
    print(f"{'='*50}\n")

    for i, item in enumerate(file_list, 1):
        print(f"\n[{i}/{total}] Processing: {item}")
        print("-" * 40)

        try:
            title = None
            if is_url:
                # Article URLs try Lightweight API first, fallback to Precision
                if not force_precision and not _url_has_file_extension(item):
                    try:
                        md_content, original_filename, _ = lightweight_url_mode(
                            item, optional_params, output_dir=output_dir)
                    except MinerUError:
                        # Fallback to Precision API
                        if token is None:
                            token = get_token()
                        md_content, original_filename, _ = url_mode(
                            item, token, optional_params, output_dir=output_dir)
                else:
                    # File URLs always need Precision API
                    if token is None:
                        token = get_token()
                    md_content, original_filename, _ = url_mode(
                        item, token, optional_params, output_dir=output_dir)

                # Use document title only for article URLs (no file extension)
                if use_title_for_url and not _url_has_file_extension(item):
                    title = extract_title(md_content)
                    if title:
                        original_filename = title

                output_path = generate_output_filename(original_filename, is_url=not title, output_dir=output_dir)
            else:
                # Auto-route files based on characteristics
                api_type, reason = get_routing_decision(item, force_precision)
                print(f"[Route] Using {'Precision' if api_type == 'precision' else 'Lightweight'} API ({reason})")

                if api_type == 'lightweight':
                    md_content, original_filename, _ = lightweight_file_mode(item, optional_params, output_dir=output_dir)
                else:
                    md_content, original_filename, _ = upload_file_mode(item, token, optional_params, output_dir=output_dir)

                output_path = generate_output_filename(original_filename, is_url=False, output_dir=output_dir)

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

    # Print summary
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


def main():
    # Handle --help-languages before argparse (since mutually exclusive group is required)
    if "--help-languages" in sys.argv:
        show_help_languages()

    parser = argparse.ArgumentParser(
        description="Convert files or URLs to markdown using MinerU APIs. "
                    "Auto-routes between Lightweight Agent API (no token needed) "
                    "and Precision API (token needed) based on file characteristics.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Convert a local file (auto-routed to Lightweight or Precision API)
  python mineru2md.py --file ./document.pdf

  # Convert a remote URL
  python mineru2md.py --url https://example.com/document.pdf

  # Specify output file
  python mineru2md.py --file ./document.pdf --output my_result.md

  # Specify output directory (for batch processing)
  python mineru2md.py --files file1.pdf file2.pdf --output-dir ./results

  # With optional parameters
  python mineru2md.py --file ./doc.pdf --enable-formula --enable-table --language en
  python mineru2md.py --url https://example.com/doc.pdf --page-ranges 1-10,20
  python mineru2md.py --file ./doc.pdf --extra-formats docx --extra-formats html

  # Force Precision API for lightweight-compatible files
  python mineru2md.py --file ./small.pdf --force-precision

  # Disable cache
  python mineru2md.py --url https://example.com/doc.pdf --no-cache

  # Set cache tolerance (seconds)
  python mineru2md.py --url https://example.com/doc.pdf --cache-tolerance 1800

  # Print markdown to stdout instead of saving to file
  python mineru2md.py --file ./document.pdf --print

  # Prepend date to output filename
  python mineru2md.py --file ./document.pdf --timestamp

  # Print with title-based filename for URL (no save)
  python mineru2md.py --url https://example.com/doc.pdf --print --timestamp

Environment:
  MINERU_TOKEN - API token for authentication (Bearer token). Only needed for Precision API.
        """
    )

    # Input mode (mutually exclusive groups)
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument("--file", "-f", help="Path to local file (PDF, DOC, PPT, XLS, images, HTML)")
    input_group.add_argument("--files", "-F", nargs="+", help="Multiple local files for batch processing")
    input_group.add_argument("--url", "-u", help="Remote URL to convert")
    input_group.add_argument("--urls", "-U", nargs="+", help="Multiple URLs for batch processing")

    # Output options
    parser.add_argument("--output", "-o", help="Output markdown file path (default: <input_name>.md)")
    parser.add_argument("--output-dir", "-d", help="Output directory for batch processing")

    # Optional parameters
    parser.add_argument("--enable-formula", action="store_true", default=None,
                        help="Enable formula recognition (default: true)")
    parser.add_argument("--disable-formula", dest="enable_formula", action="store_false", default=None,
                        help="Disable formula recognition")
    parser.add_argument("--enable-table", action="store_true", default=None,
                        help="Enable table recognition (default: true)")
    parser.add_argument("--disable-table", dest="enable_table", action="store_false", default=None,
                        help="Disable table recognition")
    parser.add_argument("--is-ocr", action="store_true", default=None,
                        help="Enable OCR (default: false)")
    parser.add_argument("--language", "-l", default="ch",
                        help="Document language (default: ch). See --help-languages for values.")
    parser.add_argument("--page-ranges", "-p", default=None,
                        help="Page range specification (e.g., '2,4-6' or '1-10')")
    parser.add_argument("--extra-formats", nargs="+", choices=["docx", "html", "latex"],
                        help="Additional export formats")
    parser.add_argument("--no-cache", action="store_true",
                        help="Bypass cache (default: false)")
    parser.add_argument("--cache-tolerance", type=int, default=None,
                        help="Cache tolerance time in seconds (default: 900)")

    # API selection
    parser.add_argument("--force-precision", action="store_true",
                        help="Force using Precision API even for lightweight-compatible files")

    # Output options
    parser.add_argument("--print", action="store_true",
                        help="Print markdown content to stdout instead of saving to file")
    parser.add_argument("--timestamp", action="store_true",
                        help="Prepend current date (YYYY-MM-DD) to output filename")

    # Polling options
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT,
                        help=f"Polling timeout in seconds (default: {DEFAULT_TIMEOUT})")

    args = parser.parse_args()

    # Build optional parameters
    optional_params = build_optional_params(args)

    # Note: Token is now fetched lazily - only when Precision API is actually needed.
    # Lightweight API does not require a token.
    token = None

    # Determine mode and process
    try:
        if args.files:
            # Batch file mode
            if args.output and not args.output_dir:
                raise MinerUError("--output is only valid for single file. Use --output-dir for batch processing.")

            # Check if any file needs Precision API
            needs_precision = args.force_precision or any(
                not is_lightweight_compatible(f) for f in args.files
            )
            if needs_precision:
                token = get_token()

            process_batch(args.files, token, optional_params, args.output_dir,
                         is_url=False, force_precision=args.force_precision,
                         use_title_for_url=False, no_save=args.print, timestamp=args.timestamp)

        elif args.urls:
            # Batch URL mode - article URLs try Lightweight first
            if args.output and not args.output_dir:
                raise MinerUError("--output is only valid for single URL. Use --output-dir for batch processing.")
            process_batch(args.urls, None, optional_params, args.output_dir, is_url=True,
                          use_title_for_url=True, no_save=args.print, timestamp=args.timestamp)

        elif args.file:
            # Single file mode - auto-route
            output_path = args.output if args.output else generate_output_filename(args.file, output_dir=args.output_dir)

            if args.timestamp and not args.output:
                output_path = _apply_timestamp(output_path)

            api_type, reason = get_routing_decision(args.file, args.force_precision)
            print(f"[Route] Using {'Precision' if api_type == 'precision' else 'Lightweight'} API ({reason})")

            if api_type == 'lightweight':
                md_content, original_filename, _ = lightweight_file_mode(args.file, optional_params, output_dir=args.output_dir)
            else:
                token = get_token()
                md_content, original_filename, _ = upload_file_mode(args.file, token, optional_params, output_dir=args.output_dir)

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
            # Single URL mode - auto-routed: article URLs try Lightweight first
            md_content, original_filename, _ = parse_with_auto_routing(
                args.url, token=None, optional_params=optional_params,
                is_url=True, force_precision=args.force_precision,
                output_dir=args.output_dir)

            if args.output:
                output_path = args.output
            else:
                # Use document title only for article URLs (no file extension)
                if not _url_has_file_extension(args.url):
                    title = extract_title(md_content)
                    if title:
                        output_path = generate_output_filename(title, is_url=False, output_dir=args.output_dir)
                    else:
                        output_path = generate_output_filename(args.url, is_url=True, output_dir=args.output_dir)
                else:
                    output_path = generate_output_filename(args.url, is_url=True, output_dir=args.output_dir)

            if args.timestamp and not args.output:
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