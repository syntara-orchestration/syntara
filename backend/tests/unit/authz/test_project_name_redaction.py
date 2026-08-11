"""Unit tests for project-name redaction helpers.

Verifies that project names are stripped from API responses when the
caller lacks project:read permission.
"""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from syntara.authz.engine import VisibilityResult, resolve_readable_project_ids
from syntara.authz.role_assignment_router import _redact_project_names
from syntara.authz.router import _ids_to_names

# ---------------------------------------------------------------------------
# _redact_project_names (pure function)
# ---------------------------------------------------------------------------


class TestRedactProjectNames:
    """Tests for the _redact_project_names helper."""

    def test_noop_when_all_readable(self) -> None:
        resources = [{"project_id": uuid4(), "project_name": "visible"}]
        _redact_project_names(resources, None)
        assert resources[0]["project_name"] == "visible"

    def test_strips_unreadable_project(self) -> None:
        readable_id = uuid4()
        hidden_id = uuid4()
        resources = [
            {"project_id": readable_id, "project_name": "allowed"},
            {"project_id": hidden_id, "project_name": "secret"},
        ]
        _redact_project_names(resources, {readable_id})
        assert resources[0]["project_name"] == "allowed"
        assert resources[1]["project_name"] is None

    def test_global_assignments_untouched(self) -> None:
        resources = [
            {"project_id": None, "project_name": None},
        ]
        _redact_project_names(resources, set())
        assert resources[0]["project_name"] is None

    def test_empty_resources(self) -> None:
        resources: list[dict[str, str]] = []
        _redact_project_names(resources, set())
        assert resources == []

    def test_all_hidden_when_empty_readable_set(self) -> None:
        pid = uuid4()
        resources = [{"project_id": pid, "project_name": "secret"}]
        _redact_project_names(resources, set())
        assert resources[0]["project_name"] is None

    def test_multiple_readable_projects(self) -> None:
        ids = [uuid4() for _ in range(3)]
        resources = [{"project_id": i, "project_name": f"p{n}"} for n, i in enumerate(ids)]
        _redact_project_names(resources, {ids[0], ids[2]})
        assert resources[0]["project_name"] == "p0"
        assert resources[1]["project_name"] is None
        assert resources[2]["project_name"] == "p2"


# ---------------------------------------------------------------------------
# VisibilityResult.readable_project_ids
# ---------------------------------------------------------------------------


class TestVisibilityResultReadableProjectIds:
    """Tests for readable_project_ids on VisibilityResult."""

    def test_none_when_unrestricted(self) -> None:
        result = VisibilityResult(unrestricted=True)
        assert result.readable_project_ids is None

    def test_defaults_to_none(self) -> None:
        result = VisibilityResult()
        assert result.readable_project_ids is None

    def test_set_explicitly(self) -> None:
        pid = uuid4()
        result = VisibilityResult(readable_project_ids={pid})
        assert result.readable_project_ids == {pid}

    def test_empty_set(self) -> None:
        result = VisibilityResult(readable_project_ids=set())
        assert result.readable_project_ids == set()


# ---------------------------------------------------------------------------
# resolve_readable_project_ids (public engine function)
# ---------------------------------------------------------------------------


class TestResolveReadableProjectIds:
    """Tests for the resolve_readable_project_ids engine function."""

    @pytest.mark.asyncio
    async def test_returns_none_when_all_readable(self) -> None:
        mock_db = AsyncMock()
        mock_evaluator = AsyncMock()
        mock_evaluator.evaluate = MagicMock(return_value={"allowed_projects": ["*"]})

        result = await resolve_readable_project_ids(
            mock_db,
            mock_evaluator,
            uuid4(),
            [],
            [],
            None,
            None,
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_empty_set_when_no_projects(self) -> None:
        mock_db = AsyncMock()
        mock_evaluator = AsyncMock()
        mock_evaluator.evaluate = MagicMock(return_value={"allowed_projects": []})

        result = await resolve_readable_project_ids(
            mock_db,
            mock_evaluator,
            uuid4(),
            [],
            [],
            None,
            None,
        )
        assert result == set()

    @pytest.mark.asyncio
    async def test_returns_project_ids(self) -> None:
        pid1, pid2 = uuid4(), uuid4()
        mock_db = AsyncMock()
        mock_exec_result = MagicMock()
        mock_exec_result.all.return_value = [MagicMock(id=pid1), MagicMock(id=pid2)]
        mock_db.exec = AsyncMock(return_value=mock_exec_result)

        mock_evaluator = AsyncMock()
        mock_evaluator.evaluate = MagicMock(return_value={"allowed_projects": ["alpha", "beta"]})

        result = await resolve_readable_project_ids(
            mock_db,
            mock_evaluator,
            uuid4(),
            [],
            [],
            None,
            None,
        )
        assert result == {pid1, pid2}


# ---------------------------------------------------------------------------
# _ids_to_names (maps UUIDs to project names)
# ---------------------------------------------------------------------------


class TestIdsToNames:
    """Tests for the _ids_to_names helper."""

    @pytest.mark.asyncio
    async def test_maps_ids_to_names(self) -> None:
        mock_db = AsyncMock()
        mock_exec_result = MagicMock()
        mock_exec_result.all.return_value = ["alpha", "beta"]
        mock_db.exec = AsyncMock(return_value=mock_exec_result)

        result = await _ids_to_names(mock_db, {uuid4(), uuid4()})
        assert result == {"alpha", "beta"}
