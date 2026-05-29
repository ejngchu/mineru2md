"""
Unit tests for mineru2md core functions.
Run with: pytest tests/ -v
"""

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

# Add parent to path for package
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from mineru2md.cli import (
    APIConfig,
    MinerUError,
    build_optional_params,
    determine_model_version,
    extract_file_extension,
    extract_title,
    generate_output_filename,
    get_file_size_mb,
    get_page_count,
    get_routing_decision,
    is_lightweight_compatible,
    validate_batch_count,
    validate_file_for_api,
)

SAMPLES_DIR = Path(__file__).parent.parent / "assets" / "samples"


# =============================================================================
# extract_file_extension
# =============================================================================

class TestExtractFileExtension:
    def test_pdf(self):
        assert extract_file_extension("doc.pdf") == "pdf"

    def test_uppercase(self):
        assert extract_file_extension("doc.PDF") == "pdf"

    def test_no_extension(self):
        assert extract_file_extension("README") == ""

    def test_multiple_dots(self):
        assert extract_file_extension("doc.old.pdf") == "pdf"


# =============================================================================
# get_file_size_mb
# =============================================================================

class TestGetFileSizeMb:
    def test_small_file(self):
        # IMG_1589.PNG should be small
        f = SAMPLES_DIR / "IMG_1589.PNG"
        if f.exists():
            size = get_file_size_mb(str(f))
            assert 0 < size < 10  # should be under 10MB


# =============================================================================
# get_page_count
# =============================================================================

class TestGetPageCount:
    def test_pdf_page_count(self):
        f = SAMPLES_DIR / "杂货铺.pdf"
        if f.exists():
            pages = get_page_count(str(f))
            assert pages is None or pages > 0

    def test_non_pdf_returns_zero(self):
        f = SAMPLES_DIR / "IMG_1589.PNG"
        if f.exists():
            pages = get_page_count(str(f))
            assert pages == 0

    def test_nonexistent_pdf(self):
        pages = get_page_count("/nonexistent/file.pdf")
        # Should return None (warning printed)
        assert pages is None


# =============================================================================
# is_lightweight_compatible
# =============================================================================

class TestIsLightweightCompatible:
    def test_image_compatible(self):
        f = SAMPLES_DIR / "IMG_1589.PNG"
        if f.exists():
            assert is_lightweight_compatible(str(f)) is True

    def test_unsupported_extension(self):
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as tmp:
            tmp.write(b"hello")
            tmp.flush()
            tmp.close()
            try:
                result = is_lightweight_compatible(tmp.name)
                assert result is False
            finally:
                os.unlink(tmp.name)

    def test_large_file(self):
        # Create a fake large file (mock size)
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(b"x" * (15 * 1024 * 1024))  # 15MB
            tmp.flush()
            tmp.close()
            try:
                result = is_lightweight_compatible(tmp.name)
                assert result is False
            finally:
                os.unlink(tmp.name)


# =============================================================================
# get_routing_decision
# =============================================================================

class TestGetRoutingDecision:
    def test_force_precision(self):
        result, reason = get_routing_decision("/some/file.pdf", force_precision=True)
        assert result == "precision"
        assert "force" in reason

    def test_lightweight_for_small_image(self):
        f = SAMPLES_DIR / "IMG_1589.PNG"
        if f.exists():
            result, reason = get_routing_decision(str(f))
            assert result == "lightweight"

    def test_precision_for_large_file(self):
        # Create a fake large file
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(b"x" * (15 * 1024 * 1024))  # 15MB
            tmp.flush()
            tmp.close()
            try:
                result, reason = get_routing_decision(tmp.name)
                assert result == "precision"
                assert "size" in reason
            finally:
                os.unlink(tmp.name)

    def test_precision_for_unsupported_type(self):
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as tmp:
            tmp.write(b"hello")
            tmp.flush()
            tmp.close()
            try:
                result, reason = get_routing_decision(tmp.name)
                assert result == "precision"
                assert "type" in reason
            finally:
                os.unlink(tmp.name)


# =============================================================================
# validate_file_for_api
# =============================================================================

class TestValidateFileForApi:
    def test_valid_file(self):
        f = SAMPLES_DIR / "IMG_1589.PNG"
        if f.exists():
            issues = validate_file_for_api(str(f))
            assert issues == []

    def test_nonexistent_file(self):
        issues = validate_file_for_api("/nonexistent/file.pdf")
        assert "not found" in issues[0].lower()

    def test_too_large(self):
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(b"x" * (201 * 1024 * 1024))  # 201MB
            tmp.flush()
            tmp.close()
            try:
                issues = validate_file_for_api(tmp.name)
                assert any("200" in i for i in issues)
            finally:
                os.unlink(tmp.name)


# =============================================================================
# validate_batch_count
# =============================================================================

class TestValidateBatchCount:
    def test_within_limit(self):
        issues = validate_batch_count(10)
        assert issues == []

    def test_exceeds_limit(self):
        issues = validate_batch_count(100)
        assert len(issues) > 0
        assert "50" in issues[0]


# =============================================================================
# generate_output_filename
# =============================================================================

class TestGenerateOutputFilename:
    def test_pdf_file(self):
        name = generate_output_filename("document.pdf")
        assert name == "document.md"

    def test_url_with_extension(self):
        name = generate_output_filename("https://example.com/file.pdf")
        assert name == "file.md"

    def test_url_without_extension(self):
        name = generate_output_filename("https://example.com/article")
        assert name == "article.md"


# =============================================================================
# extract_title
# =============================================================================

class TestExtractTitle:
    def test_valid_heading(self):
        md = "# Hello World\nSome content"
        title = extract_title(md)
        assert title == "Hello World"

    def test_no_heading(self):
        md = "Just some text"
        title = extract_title(md)
        assert title is None

    def test_heading_with_special_chars(self):
        md = "# Hello: World/Test\nContent"
        title = extract_title(md)
        # Characters \ / : * ? " < > | are replaced with _
        assert title == "Hello_ World_Test"

    def test_long_heading_truncated(self):
        md = "# " + "a" * 150 + "\nContent"
        title = extract_title(md)
        assert len(title) <= 100


# =============================================================================
# determine_model_version
# =============================================================================

class TestDetermineModelVersion:
    def test_pdf_file(self):
        result = determine_model_version("doc.pdf")
        assert result == "vlm"

    def test_html_file(self):
        result = determine_model_version("page.html")
        assert result == "MinerU-HTML"

    def test_url_with_file_extension(self):
        result = determine_model_version("https://example.com/file.pdf", is_url=True)
        assert result == "vlm"

    def test_url_without_extension(self):
        result = determine_model_version("https://example.com/article", is_url=True)
        assert result == "MinerU-HTML"


# =============================================================================
# build_optional_params
# =============================================================================

class TestBuildOptionalParams:
    def test_enable_formula(self):
        class Args:
            enable_formula = True
            enable_table = None
            is_ocr = None
            language = None
            page_ranges = None
            extra_formats = None
            no_cache = False
            cache_tolerance = None

        params = build_optional_params(Args())
        assert params.get("enable_formula") is True

    def test_disable_formula(self):
        class Args:
            enable_formula = False
            enable_table = None
            is_ocr = None
            language = None
            page_ranges = None
            extra_formats = None
            no_cache = False
            cache_tolerance = None

        params = build_optional_params(Args())
        assert params.get("enable_formula") is False

    def test_language(self):
        class Args:
            enable_formula = None
            enable_table = None
            is_ocr = None
            language = "en"
            page_ranges = None
            extra_formats = None
            no_cache = False
            cache_tolerance = None

        params = build_optional_params(Args())
        assert params.get("language") == "en"

    def test_page_ranges(self):
        class Args:
            enable_formula = None
            enable_table = None
            is_ocr = None
            language = None
            page_ranges = "1-10,15"
            extra_formats = None
            no_cache = False
            cache_tolerance = None

        params = build_optional_params(Args())
        assert params.get("page_ranges") == "1-10,15"


# =============================================================================
# validate_args (imported separately since it uses argparse)
# =============================================================================

class TestValidateArgs:
    def test_negative_timeout(self):
        from mineru2md.cli import validate_args, MinerUError
        class Args:
            timeout = -5
            output = None
            page_ranges = None
            cache_tolerance = None
        try:
            validate_args(Args())
            assert False, "Should have raised"
        except MinerUError as e:
            assert "timeout" in str(e).lower()

    def test_invalid_page_ranges(self):
        from mineru2md.cli import validate_args, MinerUError
        class Args:
            timeout = 300
            output = None
            page_ranges = "invalid"
            cache_tolerance = None
        try:
            validate_args(Args())
            assert False, "Should have raised"
        except MinerUError as e:
            assert "page-ranges" in str(e).lower()

    def test_valid_page_ranges(self):
        from mineru2md.cli import validate_args
        class Args:
            timeout = 300
            output = None
            page_ranges = "1-10,15,20-25"
            cache_tolerance = None
        validate_args(Args())  # Should not raise

    def test_output_not_directory(self):
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp.write(b"x")
            tmp.flush()
            tmp.close()
            from mineru2md.cli import validate_args, MinerUError
            class Args:
                timeout = 300
                output = tmp.name
                page_ranges = None
                cache_tolerance = None
            try:
                validate_args(Args())
                assert False, "Should have raised"
            except MinerUError as e:
                assert "directory" in str(e).lower()
            finally:
                os.unlink(tmp.name)


# =============================================================================
# Config file auto-creation (get_token when config.json missing)
# =============================================================================

class TestConfigFileAutoCreation:
    """Test that config.json is auto-created when missing."""

    def test_config_created_when_missing(self):
        import json
        import shutil
        from unittest.mock import patch

        from mineru2md.cli import get_token, MinerUError

        # Use a temp dir for the fake config path
        tmp_base = tempfile.mkdtemp()
        fake_config_path = Path(tmp_base) / ".config" / "mineru2md" / "config.json"

        try:
            with patch("mineru2md.cli._get_config_path", return_value=fake_config_path):
                with patch.dict(os.environ, {}, clear=True):
                    try:
                        get_token()
                        assert False, "Should have raised MinerUError"
                    except MinerUError:
                        pass  # expected, token is empty

                    # Config file should have been auto-created
                    assert fake_config_path.exists(), "config.json should be auto-created"
                    with open(fake_config_path, "r", encoding="utf-8") as f:
                        config = json.load(f)
                    assert "mineru_token" in config or "token" in config
                    assert config.get("mineru_token") == "" or config.get("token") == ""
        finally:
            shutil.rmtree(tmp_base, ignore_errors=True)

    def test_existing_config_with_token_loaded(self):
        import json
        import shutil
        from unittest.mock import patch

        from mineru2md.cli import get_token

        tmp_base = tempfile.mkdtemp()
        fake_config_path = Path(tmp_base) / ".config" / "mineru2md" / "config.json"
        fake_config_path.parent.mkdir(parents=True)
        fake_config_path.write_text(json.dumps({"mineru_token": "test_token_123"}), encoding="utf-8")

        try:
            with patch("mineru2md.cli._get_config_path", return_value=fake_config_path):
                with patch.dict(os.environ, {}, clear=True):
                    token = get_token()
                    assert token == "test_token_123"
        finally:
            shutil.rmtree(tmp_base, ignore_errors=True)

    def test_env_var_takes_priority_over_config(self):
        import shutil
        from unittest.mock import patch

        from mineru2md.cli import get_token

        tmp_base = tempfile.mkdtemp()
        fake_config_path = Path(tmp_base) / ".config" / "mineru2md" / "config.json"
        fake_config_path.parent.mkdir(parents=True)
        fake_config_path.write_text('{"mineru_token": "file_token"}', encoding="utf-8")

        try:
            with patch("mineru2md.cli._get_config_path", return_value=fake_config_path):
                with patch.dict(os.environ, {"MINERU_TOKEN": "env_token"}):
                    token = get_token()
                    assert token == "env_token"
        finally:
            shutil.rmtree(tmp_base, ignore_errors=True)

    def test_config_created_even_when_token_in_env(self):
        """When MINERU_TOKEN is set but config.json is missing, config should still be created with token pre-filled."""
        import json
        import shutil
        from unittest.mock import patch

        from mineru2md.cli import get_token

        tmp_base = tempfile.mkdtemp()
        fake_config_path = Path(tmp_base) / ".config" / "mineru2md" / "config.json"

        try:
            with patch("mineru2md.cli._get_config_path", return_value=fake_config_path):
                with patch.dict(os.environ, {"MINERU_TOKEN": "env_token_abc"}):
                    token = get_token()
                    assert token == "env_token_abc"
                    # Config file should be created with token pre-filled
                    assert fake_config_path.exists(), "config.json should be auto-created even with env token"
                    with open(fake_config_path, "r", encoding="utf-8") as f:
                        config = json.load(f)
                    assert "mineru_token" in config
                    assert config["mineru_token"] == "env_token_abc", "token should be pre-filled from env"
        finally:
            shutil.rmtree(tmp_base, ignore_errors=True)

    def test_existing_config_with_empty_token_backfilled_by_env(self):
        """Config exists with empty mineru_token, env token set → should backfill config."""
        import json
        import shutil
        from unittest.mock import patch

        from mineru2md.cli import get_token

        tmp_base = tempfile.mkdtemp()
        fake_config_path = Path(tmp_base) / ".config" / "mineru2md" / "config.json"
        fake_config_path.parent.mkdir(parents=True)
        fake_config_path.write_text(json.dumps({"mineru_token": ""}), encoding="utf-8")

        try:
            with patch("mineru2md.cli._get_config_path", return_value=fake_config_path):
                with patch.dict(os.environ, {"MINERU_TOKEN": "env_backfill_token"}):
                    token = get_token()
                    assert token == "env_backfill_token"
                    # Config should be backfilled
                    with open(fake_config_path, "r", encoding="utf-8") as f:
                        config = json.load(f)
                    assert config["mineru_token"] == "env_backfill_token", "empty token should be backfilled from env"
        finally:
            shutil.rmtree(tmp_base, ignore_errors=True)

    def test_existing_config_with_nonempty_token_not_overwritten(self):
        """Config exists with non-empty mineru_token, env token set → should NOT overwrite config."""
        import json
        import shutil
        from unittest.mock import patch

        from mineru2md.cli import get_token

        tmp_base = tempfile.mkdtemp()
        fake_config_path = Path(tmp_base) / ".config" / "mineru2md" / "config.json"
        fake_config_path.parent.mkdir(parents=True)
        fake_config_path.write_text(json.dumps({"mineru_token": "file_token"}), encoding="utf-8")

        try:
            with patch("mineru2md.cli._get_config_path", return_value=fake_config_path):
                with patch.dict(os.environ, {"MINERU_TOKEN": "env_token"}):
                    token = get_token()
                    assert token == "env_token", "env token takes priority"
                    # Config should NOT be overwritten
                    with open(fake_config_path, "r", encoding="utf-8") as f:
                        config = json.load(f)
                    assert config["mineru_token"] == "file_token", "config token should NOT be overwritten"
        finally:
            shutil.rmtree(tmp_base, ignore_errors=True)
        """_get_config_path should always return ~/.config/mineru2md/config.json on all platforms."""
        import shutil
        from unittest.mock import patch

        from mineru2md.cli import _get_config_path

        tmp_base = tempfile.mkdtemp()
        fake_home = Path(tmp_base)

        try:
            with patch("pathlib.Path.home", return_value=fake_home):
                path = _get_config_path()
                assert path is not None
                assert ".config" in path.parts
                assert "mineru2md" in path.parts
                assert "config.json" in path.parts
                assert str(fake_home) in str(path)
        finally:
            shutil.rmtree(tmp_base, ignore_errors=True)
