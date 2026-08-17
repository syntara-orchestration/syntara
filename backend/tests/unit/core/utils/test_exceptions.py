"""Unit tests for exception utilities."""

from syntara.core.utils.exceptions import extract_all_exceptions


class TestExtractAllExceptions:
    """Tests for extract_all_exceptions function."""

    def test_single_exception(self) -> None:
        """Test extraction from ExceptionGroup with single exception."""
        error = ValueError("test error")
        group = ExceptionGroup("test group", [error])

        result = extract_all_exceptions(group)

        assert len(result) == 1
        assert result[0] is error

    def test_multiple_exceptions(self) -> None:
        """Test extraction from ExceptionGroup with multiple exceptions."""
        error1 = ValueError("error 1")
        error2 = TypeError("error 2")
        error3 = RuntimeError("error 3")
        group = ExceptionGroup("test group", [error1, error2, error3])

        result = extract_all_exceptions(group)

        assert len(result) == 3
        assert error1 in result
        assert error2 in result
        assert error3 in result

    def test_nested_exception_groups(self) -> None:
        """Test extraction from nested ExceptionGroups."""
        error1 = ValueError("error 1")
        error2 = TypeError("error 2")
        error3 = RuntimeError("error 3")
        error4 = KeyError("error 4")

        inner_group = ExceptionGroup("inner group", [error2, error3])
        outer_group = ExceptionGroup("outer group", [error1, inner_group, error4])

        result = extract_all_exceptions(outer_group)

        assert len(result) == 4
        assert error1 in result
        assert error2 in result
        assert error3 in result
        assert error4 in result

    def test_deeply_nested_exception_groups(self) -> None:
        """Test extraction from deeply nested ExceptionGroups."""
        error1 = ValueError("level 1")
        error2 = TypeError("level 2")
        error3 = RuntimeError("level 3")

        level3_group = ExceptionGroup("level 3", [error3])
        level2_group = ExceptionGroup("level 2", [error2, level3_group])
        level1_group = ExceptionGroup("level 1", [error1, level2_group])

        result = extract_all_exceptions(level1_group)

        assert len(result) == 3
        assert error1 in result
        assert error2 in result
        assert error3 in result

    def test_mixed_nested_structure(self) -> None:
        """Test extraction from complex mixed nested structure."""
        # Create various errors
        errors = [
            ValueError("error 1"),
            TypeError("error 2"),
            RuntimeError("error 3"),
            KeyError("error 4"),
            AttributeError("error 5"),
            IndexError("error 6"),
        ]

        # Create nested structure:
        # root_group
        # ├── errors[0]
        # ├── sub_group1
        # │   ├── errors[1]
        # │   └── sub_sub_group
        # │       ├── errors[2]
        # │       └── errors[3]
        # ├── errors[4]
        # └── sub_group2
        #     └── errors[5]

        sub_sub_group = ExceptionGroup("sub-sub", [errors[2], errors[3]])
        sub_group1 = ExceptionGroup("sub1", [errors[1], sub_sub_group])
        sub_group2 = ExceptionGroup("sub2", [errors[5]])
        root_group = ExceptionGroup("root", [errors[0], sub_group1, errors[4], sub_group2])

        result = extract_all_exceptions(root_group)

        assert len(result) == 6
        for error in errors:
            assert error in result
