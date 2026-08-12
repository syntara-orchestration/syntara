"""Unit tests for _sanitize_filename in the workflow router."""

from syntara.workflows.router import _sanitize_filename


class TestSanitizeFilename:
    """Tests for the _sanitize_filename helper."""

    def test_passes_through_safe_characters(self) -> None:
        assert _sanitize_filename("my-workflow.v1") == "my-workflow.v1"

    def test_replaces_spaces_and_special_chars(self) -> None:
        assert _sanitize_filename("my workflow!@#") == "my_workflow___"

    def test_replaces_slashes(self) -> None:
        assert _sanitize_filename("path/to/workflow") == "path_to_workflow"

    def test_truncates_to_200_chars(self) -> None:
        long_name = "a" * 300
        result = _sanitize_filename(long_name)
        assert len(result) == 200

    def test_empty_string_returns_fallback(self) -> None:
        assert _sanitize_filename("") == "workflow"

    def test_all_special_chars_returns_fallback(self) -> None:
        result = _sanitize_filename("!!!")
        assert result == "___"
