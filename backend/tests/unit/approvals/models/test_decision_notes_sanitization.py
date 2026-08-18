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
            # Double-encoded HTML (e.g. &amp;lt; → &lt; → <)
            ("&amp;lt;script&amp;gt;alert(1)&amp;lt;/script&amp;gt;", ""),
            ("&amp;lt;img src=x onerror=alert(1)&amp;gt;", ""),
            # Triple-encoded HTML
            ("&amp;amp;lt;script&amp;amp;gt;alert(1)&amp;amp;lt;/script&amp;amp;gt;", ""),
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
            "double-encoded-script",
            "double-encoded-img-onerror",
            "triple-encoded-script",
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
            "&amp;lt;script&amp;gt;alert(1)&amp;lt;/script&amp;gt;",
            "&amp;lt;img src=x onerror=alert(1)&amp;gt;",
            "&amp;amp;lt;script&amp;amp;gt;alert(1)&amp;amp;lt;/script&amp;amp;gt;",
        ],
        ids=[
            "script",
            "nested-script",
            "triple-nested",
            "img-onerror",
            "unclosed",
            "bold",
            "svg",
            "double-encoded-script",
            "double-encoded-img",
            "triple-encoded-script",
        ],
    )
    def test_result_contains_no_tag_like_sequences(self, raw: str) -> None:
        """Post-condition: sanitized output must not contain tag-like sequences."""
        request = ApprovalDecisionRequest(status="approved", notes=raw)
        assert not _TAG_LIKE_RE.search(request.notes or "")

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
            "&amp;lt;script&amp;gt;alert(1)&amp;lt;/script&amp;gt;",
            "&amp;lt;img src=x onerror=alert(1)&amp;gt;",
            "&amp;amp;lt;script&amp;amp;gt;alert(1)&amp;amp;lt;/script&amp;amp;gt;",
        ],
        ids=[
            "script",
            "nested-script",
            "triple-nested",
            "img-onerror",
            "unclosed",
            "bold",
            "svg",
            "double-encoded-script",
            "double-encoded-img",
            "triple-encoded-script",
        ],
    )
    def test_batch_result_contains_no_tag_like_sequences(self, raw: str) -> None:
        """Post-condition: batch model sanitized output must not contain tag-like sequences."""
        decision = BatchApprovalDecision(approval_id=uuid4(), status="approved", notes=raw)
        assert not _TAG_LIKE_RE.search(decision.notes or "")

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("<script>alert('xss')</script>", ""),
            ('<img src=x onerror="alert(1)">', ""),
            ("clean text", "clean text"),
            ("<<script>script>alert(1)</script>", "<"),
            ("&lt;script&gt;alert(1)&lt;/script&gt;", ""),
            ("&amp;lt;script&amp;gt;alert(1)&amp;lt;/script&amp;gt;", ""),
            ("&amp;amp;lt;script&amp;amp;gt;alert(1)&amp;amp;lt;/script&amp;amp;gt;", ""),
            ("Tom & Jerry", "Tom & Jerry"),
        ],
        ids=[
            "script-tag",
            "img-onerror",
            "clean-text",
            "nested-obfuscated",
            "entity-encoded",
            "double-encoded",
            "triple-encoded",
            "plain-text-special-chars",
        ],
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

    def test_near_limit_encoded_input_accepted(self) -> None:
        """_SANITIZE_MAX_ROUNDS - 1 layers must converge via the final check, not reject."""
        from syntara.approvals.models.api_models import _SANITIZE_MAX_ROUNDS

        payload = "<script>alert(1)</script>"
        for _ in range(_SANITIZE_MAX_ROUNDS - 1):
            payload = payload.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        request = ApprovalDecisionRequest(status="approved", notes=payload)
        assert request.notes == ""

    def test_boundary_encoded_input_rejected_with_422(self) -> None:
        """N encoding layers leave real HTML tags in result — must reject."""
        from syntara.approvals.models.api_models import _SANITIZE_MAX_ROUNDS

        payload = "<script>alert(1)</script>"
        for _ in range(_SANITIZE_MAX_ROUNDS):
            payload = payload.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        with pytest.raises(ValidationError, match="deeply nested HTML encoding"):
            ApprovalDecisionRequest(status="approved", notes=payload)

    def test_deeply_encoded_input_rejected_with_422(self) -> None:
        """Input encoded beyond _SANITIZE_MAX_ROUNDS must be rejected, not stored partially decoded."""
        from syntara.approvals.models.api_models import _SANITIZE_MAX_ROUNDS

        payload = "<script>alert(1)</script>"
        for _ in range(_SANITIZE_MAX_ROUNDS + 1):
            payload = payload.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        with pytest.raises(ValidationError, match="deeply nested HTML encoding"):
            ApprovalDecisionRequest(status="approved", notes=payload)

    def test_batch_deeply_encoded_input_rejected_with_422(self) -> None:
        """Batch model must also reject deeply encoded input."""
        from syntara.approvals.models.api_models import _SANITIZE_MAX_ROUNDS

        payload = "<script>alert(1)</script>"
        for _ in range(_SANITIZE_MAX_ROUNDS + 1):
            payload = payload.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        with pytest.raises(ValidationError, match="deeply nested HTML encoding"):
            BatchApprovalDecision(approval_id=uuid4(), status="approved", notes=payload)


class TestDecisionNotesAlias:
    """Both request models accept ``notes`` and its ``decision_notes`` alias (AAP-87655).

    The response schema returns the field as ``decision_notes``; consumers that model
    their request on the response previously lost the value silently. Both keys must now
    populate the same ``notes`` field, and sanitization must still run through the alias.
    """

    def test_single_accepts_decision_notes_alias(self) -> None:
        request = ApprovalDecisionRequest.model_validate({"status": "approved", "decision_notes": "looks good"})
        assert request.notes == "looks good"

    def test_single_accepts_canonical_notes(self) -> None:
        request = ApprovalDecisionRequest.model_validate({"status": "approved", "notes": "looks good"})
        assert request.notes == "looks good"

    def test_single_both_keys_produce_identical_result(self) -> None:
        by_notes = ApprovalDecisionRequest.model_validate({"status": "approved", "notes": "same"})
        by_alias = ApprovalDecisionRequest.model_validate({"status": "approved", "decision_notes": "same"})
        assert by_notes.notes == by_alias.notes == "same"

    def test_single_alias_input_is_sanitized(self) -> None:
        """Sanitization runs on the field regardless of which alias supplied the value."""
        request = ApprovalDecisionRequest.model_validate(
            {"status": "approved", "decision_notes": "<script>alert(1)</script>keep"}
        )
        assert request.notes == "keep"

    def test_batch_accepts_decision_notes_alias(self) -> None:
        decision = BatchApprovalDecision.model_validate(
            {"approval_id": str(uuid4()), "status": "approved", "decision_notes": "batch note"}
        )
        assert decision.notes == "batch note"

    def test_batch_both_keys_produce_identical_result(self) -> None:
        approval_id = str(uuid4())
        by_notes = BatchApprovalDecision.model_validate(
            {"approval_id": approval_id, "status": "approved", "notes": "same"}
        )
        by_alias = BatchApprovalDecision.model_validate(
            {"approval_id": approval_id, "status": "approved", "decision_notes": "same"}
        )
        assert by_notes.notes == by_alias.notes == "same"

    def test_batch_alias_input_is_sanitized(self) -> None:
        decision = BatchApprovalDecision.model_validate(
            {"approval_id": str(uuid4()), "status": "approved", "decision_notes": "<b>bold</b> note"}
        )
        assert decision.notes == "bold note"
