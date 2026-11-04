"""Unit tests for core/utils/security.py CSS validation."""

import pytest

from syntara.core.utils.security import normalize_css, validate_css_security


class TestNormalizeCss:
    """Tests for CSS normalization."""

    def test_strips_comments(self) -> None:
        """CSS comments are stripped."""
        assert normalize_css("background: url/**/(http://evil.com);") == "background: url(http://evil.com);"
        assert normalize_css("behavior/**/: url(x.htc);") == "behavior: url(x.htc);"

    def test_normalizes_numeric_hex_escapes(self) -> None:
        """Numeric hex escapes are converted to characters."""
        assert normalize_css(r"\75rl(http://evil.com)") == "url(http://evil.com)"
        assert normalize_css(r"\40import") == "@import"

    def test_normalizes_identity_escapes(self) -> None:
        """Identity escapes are resolved to their characters."""
        assert normalize_css(r"u\rl(http://evil.com)") == "url(http://evil.com)"
        assert normalize_css(r"@\import") == "@import"

    def test_handles_invalid_codepoints(self) -> None:
        """Codepoints above U+10FFFF are replaced with U+FFFD."""
        # U+110000 is above the max valid codepoint
        assert normalize_css(r"\110000") == "�"

    def test_safe_css_unchanged(self) -> None:
        """Safe CSS passes through unchanged."""
        safe_css = ".form { color: blue; font-size: 14px; }"
        assert normalize_css(safe_css) == safe_css


class TestValidateCssSecurity:
    """Tests for CSS security validation."""

    def test_rejects_url(self) -> None:
        """url() is rejected."""
        with pytest.raises(ValueError, match=r"url\(\).*exfiltration"):
            validate_css_security("background: url(http://evil.com);")

    def test_rejects_url_with_unicode_escape(self) -> None:
        """url() via unicode escape is rejected."""
        with pytest.raises(ValueError, match=r"url\(\).*exfiltration"):
            validate_css_security(r"background: \75rl(http://evil.com);")

    def test_rejects_url_with_identity_escape(self) -> None:
        """url() via identity escape is rejected."""
        with pytest.raises(ValueError, match=r"url\(\).*exfiltration"):
            validate_css_security(r"background: u\rl(http://evil.com);")

    def test_rejects_url_with_comment_bypass(self) -> None:
        """url() via comment bypass is rejected."""
        with pytest.raises(ValueError, match=r"url\(\).*exfiltration"):
            validate_css_security("background: url/**/(http://evil.com);")

    def test_rejects_import(self) -> None:
        """@import is rejected."""
        with pytest.raises(ValueError, match=r"@import.*external"):
            validate_css_security("@import 'evil.css';")

    def test_rejects_import_with_escape(self) -> None:
        """@import via escape is rejected."""
        with pytest.raises(ValueError, match=r"@import.*external"):
            validate_css_security(r"@\import 'evil.css';")

    def test_rejects_attribute_selector(self) -> None:
        """Attribute selectors are rejected."""
        with pytest.raises(ValueError, match=r"attribute selectors.*exfiltration"):
            validate_css_security("input[value^='a'] { background: red; }")

    def test_rejects_attribute_selector_with_escape(self) -> None:
        """Attribute selectors via escape are rejected."""
        with pytest.raises(ValueError, match=r"attribute selectors.*exfiltration"):
            validate_css_security(r"input\[value^='a'\] { background: red; }")

    def test_rejects_expression(self) -> None:
        """expression() is rejected."""
        with pytest.raises(ValueError, match=r"expression\(\).*code execution"):
            validate_css_security("width: expression(alert(1));")

    def test_rejects_expression_with_escape(self) -> None:
        """expression() via escape is rejected."""
        with pytest.raises(ValueError, match=r"expression\(\).*code execution"):
            validate_css_security(r"width: \65xpression(1+1);")

    def test_rejects_behavior(self) -> None:
        """behavior: is rejected."""
        with pytest.raises(ValueError, match=r"behavior:.*code execution"):
            validate_css_security("behavior: none;")

    def test_rejects_behavior_with_escape(self) -> None:
        """behavior: via escape is rejected."""
        with pytest.raises(ValueError, match=r"behavior:.*code execution"):
            validate_css_security(r"\62 ehavior: none;")

    def test_accepts_safe_css(self) -> None:
        """Safe CSS is accepted."""
        validate_css_security(".form { color: blue; font-size: 14px; margin: 10px; }")
        validate_css_security("body { background-color: #f0f0f0; }")
        validate_css_security(".button { padding: 10px 20px; border-radius: 5px; }")
