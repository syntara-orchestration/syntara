"""Unit tests for XSS sanitization of approval decision notes.

Validates that HTML tags are stripped from notes in both single and batch
approval decision request models.
"""

import re
from uuid import uuid4

import pytest
from pydantic import ValidationError

from syntara.approvals.models.api_models import (
    ApprovalDecisionRequest,
    BatchApprovalDecision,
)

_TAG_LIKE_RE = re.compile(r"</?[a-zA-Z]")


class TestDecisionNotesSanitization:
    """Test HTML tag stripping on approval decision notes."""

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("<script>alert('xss')</script>", ""),
            ('<img src=x onerror="alert(1)">', ""),
            ("<b>bold</b> text", "bold text"),
            ("<div><p>nested</p></div>", "nested"),
            ("clean text", "clean text"),
            ("a < b and c > d", "a < b and c > d"),
            ("", ""),
            ('<a href="javascript:alert(1)">click</a>', "click"),
            ("Hello<script>document.cookie</script>World", "HelloWorld"),
            ("<SCRIPT>alert('case')</SCRIPT>", ""),
            ('<svg onload="alert(1)">', ""),
            ("<iframe src=evil></iframe>", ""),
            ("&lt;script&gt;alert(1)&lt;/script&gt;", ""),
            # Nested/obfuscated tag bypass (single-pass regex failure)
            ("<<script>script>alert(1)</script>", "<"),
            ("<<<script>>script>alert(1)</script>", "<<"),
            # Unclosed tags
            ("<script", ""),
            ("<img src=x onerror=alert(1)", ""),
            ("<div", ""),
            # Mixed nested and normal
            ("<b>hello</b> <<b>b>world</b>", "hello world"),
            # Plain text with special characters preserved (not entity-encoded)
            ("Tom & Jerry", "Tom & Jerry"),
            ("cost < 100", "cost < 100"),
            ("profit > 50 & loss < 10", "profit > 50 & loss < 10"),
        ],
        ids=[
            "script-tag",
            "img-onerror",
            "bold-tag",
            "nested-tags",
            "clean-text",
            "angle-brackets-in-text",
            "empty-string",
            "javascript-href",
            "inline-script",
            "uppercase-script",
            "svg-onload",
            "iframe",
            "entity-encoded-html-stripped",
            "nested-obfuscated-script",
            "triple-nested-obfuscated",
            "unclosed-script",
            "unclosed-img-onerror",
            "unclosed-div",
            "mixed-nested-normal",
            "ampersand-in-text",
            "less-than-in-text",
            "mixed-special-chars",
        ],
    )
    def test_single_decision_strips_html(self, raw: str, expected: str) -> None:
        request = ApprovalDecisionRequest(status="approved", notes=raw)
        assert request.notes == expected

    @pytest.mark.parametrize(
        "raw",
        [
            "<script>alert(1)</script>",
            "<<script>script>alert(1)</script>",
            "<<<script>>script>alert(1)</script>",
            '<img src=x onerror="alert(1)">',
            "<script",
            "<b>text</b>",
            '<svg onload="alert(1)">',
        ],
        ids=[
            "script",
            "nested-script",
            "triple-nested",
            "img-onerror",
            "unclosed",
            "bold",
            "svg",
        ],
    )
    def test_result_contains_no_tag_like_sequences(self, raw: str) -> None:
        """Post-condition: sanitized output must not contain tag-like sequences."""
        request = ApprovalDecisionRequest(status="approved", notes=raw)
        assert not _TAG_LIKE_RE.search(request.notes or "")

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("<script>alert('xss')</script>", ""),
            ('<img src=x onerror="alert(1)">', ""),
            ("clean text", "clean text"),
            ("<<script>script>alert(1)</script>", "<"),
        ],
        ids=["script-tag", "img-onerror", "clean-text", "nested-obfuscated"],
    )
    def test_batch_decision_strips_html(self, raw: str, expected: str) -> None:
        decision = BatchApprovalDecision(approval_id=uuid4(), status="approved", notes=raw)
        assert decision.notes == expected

    def test_none_notes_pass_through(self) -> None:
        request = ApprovalDecisionRequest(status="approved", notes=None)
        assert request.notes is None

    def test_omitted_notes_default_none(self) -> None:
        request = ApprovalDecisionRequest(status="approved")
        assert request.notes is None

    def test_batch_none_notes_pass_through(self) -> None:
        decision = BatchApprovalDecision(approval_id=uuid4(), status="approved", notes=None)
        assert decision.notes is None

    def test_batch_omitted_notes_default_none(self) -> None:
        decision = BatchApprovalDecision(approval_id=uuid4(), status="approved")
        assert decision.notes is None

    def test_non_string_notes_rejected_with_422(self) -> None:
        with pytest.raises(ValidationError):
            ApprovalDecisionRequest(status="approved", notes=123)

    def test_max_length_still_enforced_after_stripping(self) -> None:
        long_text = "a" * 2001
        with pytest.raises(ValidationError, match="at most 2000"):
            ApprovalDecisionRequest(status="approved", notes=long_text)

    def test_stripping_reduces_below_max_length(self) -> None:
        """Tags stripped before length check, so tagged content fitting after strip passes."""
        inner = "a" * 1990
        tagged = f"<b>{inner}</b>"
        request = ApprovalDecisionRequest(status="approved", notes=tagged)
        assert request.notes == inner
