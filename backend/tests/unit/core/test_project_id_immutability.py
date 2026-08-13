"""Unit tests for assert_project_id_unchanged guard (AAP-79246)."""

from uuid import uuid4

import pytest

from syntara.core.exceptions import SafeValueError, assert_project_id_unchanged


class TestAssertProjectIdUnchanged:
    """Verify the project_id immutability guard."""

    def test_raises_when_project_id_changes(self) -> None:
        current = uuid4()
        different = uuid4()
        with pytest.raises(SafeValueError, match="immutable"):
            assert_project_id_unchanged(current, different)

    def test_allows_same_project_id(self) -> None:
        project_id = uuid4()
        assert_project_id_unchanged(project_id, project_id)

    def test_allows_none_requested(self) -> None:
        assert_project_id_unchanged(uuid4(), None)

    def test_allows_both_none(self) -> None:
        assert_project_id_unchanged(None, None)

    def test_raises_when_current_is_none_but_requested_is_set(self) -> None:
        requested = uuid4()
        with pytest.raises(SafeValueError, match="immutable"):
            assert_project_id_unchanged(None, requested)
