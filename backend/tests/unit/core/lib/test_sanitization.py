"""Unit tests for shared sanitization utilities."""

from syntara.core.lib.sanitization import escape_control_chars, has_control_chars, strip_control_chars


class TestStripControlChars:
    """Tests for strip_control_chars function."""

    def test_normal_string_unchanged(self) -> None:
        assert strip_control_chars("hello world") == "hello world"

    def test_strips_newline(self) -> None:
        assert strip_control_chars("user\n@example.com") == "user@example.com"

    def test_strips_carriage_return(self) -> None:
        assert strip_control_chars("user\r@example.com") == "user@example.com"

    def test_strips_crlf(self) -> None:
        assert strip_control_chars("user\r\n@example.com") == "user@example.com"

    def test_strips_null_byte(self) -> None:
        assert strip_control_chars("user\x00name") == "username"

    def test_strips_tab(self) -> None:
        assert strip_control_chars("user\tname") == "username"

    def test_strips_del_character(self) -> None:
        assert strip_control_chars("user\x7fname") == "username"

    def test_strips_mixed_control_chars(self) -> None:
        assert strip_control_chars("a\nb\rc\td\x00e") == "abcde"

    def test_empty_string(self) -> None:
        assert strip_control_chars("") == ""

    def test_only_control_chars_returns_empty(self) -> None:
        assert strip_control_chars("\n\r\t\x00") == ""

    def test_preserves_non_ascii_unicode(self) -> None:
        assert strip_control_chars("José García") == "José García"

    def test_preserves_cjk_characters(self) -> None:
        assert strip_control_chars("用户名") == "用户名"

    def test_strips_trailing_newline(self) -> None:
        assert strip_control_chars("user17\n") == "user17"

    def test_preserves_space(self) -> None:
        assert strip_control_chars("Test User") == "Test User"


class TestHasControlChars:
    """Tests for has_control_chars function."""

    def test_clean_string(self) -> None:
        assert has_control_chars("hello world") is False

    def test_empty_string(self) -> None:
        assert has_control_chars("") is False

    def test_detects_newline(self) -> None:
        assert has_control_chars("user\n") is True

    def test_detects_null_byte(self) -> None:
        assert has_control_chars("user\x00name") is True

    def test_detects_tab(self) -> None:
        assert has_control_chars("user\tname") is True

    def test_detects_del(self) -> None:
        assert has_control_chars("user\x7fname") is True

    def test_preserves_non_ascii_unicode(self) -> None:
        assert has_control_chars("José García") is False

    def test_space_is_not_control(self) -> None:
        assert has_control_chars("Test User") is False


class TestEscapeControlChars:
    """Tests for escape_control_chars function."""

    def test_normal_string_unchanged(self) -> None:
        assert escape_control_chars("hello world") == "hello world"

    def test_escapes_newline(self) -> None:
        assert escape_control_chars("user\n@example.com") == "user\\n@example.com"

    def test_escapes_carriage_return(self) -> None:
        assert escape_control_chars("user\r@example.com") == "user\\r@example.com"

    def test_escapes_tab(self) -> None:
        assert escape_control_chars("user\tname") == "user\\tname"

    def test_escapes_null_byte(self) -> None:
        assert escape_control_chars("user\x00name") == "user\\x00name"

    def test_escapes_del_character(self) -> None:
        assert escape_control_chars("user\x7fname") == "user\\x7fname"

    def test_escapes_mixed_control_chars(self) -> None:
        assert escape_control_chars("a\nb\rc\td\x00e") == "a\\nb\\rc\\td\\x00e"

    def test_empty_string(self) -> None:
        assert escape_control_chars("") == ""

    def test_only_control_chars(self) -> None:
        assert escape_control_chars("\n\r\t\x00") == "\\n\\r\\t\\x00"

    def test_preserves_non_ascii_unicode(self) -> None:
        assert escape_control_chars("José García") == "José García"

    def test_preserves_cjk_characters(self) -> None:
        assert escape_control_chars("用户名") == "用户名"

    def test_preserves_space(self) -> None:
        assert escape_control_chars("Test User") == "Test User"

    def test_escapes_low_control_chars(self) -> None:
        assert escape_control_chars("a\x01b\x02c") == "a\\x01b\\x02c"
