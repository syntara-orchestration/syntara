"""Unit tests for who_can helper functions in syntara.authz.router."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Select
from sqlmodel import select

from syntara.authz.router import (
    WhoCanRequest,
    WhoCanUser,
    _apply_who_can_cursor_filter,
    _build_page_cursors,
    _check_batch_authorization,
    _check_user_authorized,
    _count_batch_authorized,
)
from syntara.core.models.user import User
from syntara.core.utils.cursor import PaginationDirection, SortDirection

# ---------------------------------------------------------------------------
# _apply_who_can_cursor_filter
# ---------------------------------------------------------------------------


class TestApplyWhoCanCursorFilter:
    """Tests for _apply_who_can_cursor_filter."""

    def _base_query(self) -> Select[tuple[User]]:
        return select(User)

    def test_id_sort_forward_asc(self) -> None:
        cursor_id = uuid4()
        result = _apply_who_can_cursor_filter(
            self._base_query(),
            sort_field="id",
            sort_direction=SortDirection.ASC,
            direction=PaginationDirection.NEXT,
            cursor_id=cursor_id,
            cursor_sort_value=None,
        )
        where_clause = str(result.whereclause)
        assert ">" in where_clause

    def test_id_sort_forward_desc(self) -> None:
        cursor_id = uuid4()
        result = _apply_who_can_cursor_filter(
            self._base_query(),
            sort_field="id",
            sort_direction=SortDirection.DESC,
            direction=PaginationDirection.NEXT,
            cursor_id=cursor_id,
            cursor_sort_value=None,
        )
        where_clause = str(result.whereclause)
        assert "<" in where_clause

    def test_id_sort_backward_asc(self) -> None:
        cursor_id = uuid4()
        result = _apply_who_can_cursor_filter(
            self._base_query(),
            sort_field="id",
            sort_direction=SortDirection.ASC,
            direction=PaginationDirection.PREV,
            cursor_id=cursor_id,
            cursor_sort_value=None,
        )
        where_clause = str(result.whereclause)
        assert "<" in where_clause

    def test_username_sort_no_cursor_value_returns_unchanged(self) -> None:
        base = self._base_query()
        result = _apply_who_can_cursor_filter(
            base,
            sort_field="username",
            sort_direction=SortDirection.ASC,
            direction=PaginationDirection.NEXT,
            cursor_id=uuid4(),
            cursor_sort_value=None,
        )
        assert str(result) == str(base)

    def test_username_sort_forward_asc(self) -> None:
        cursor_id = uuid4()
        result = _apply_who_can_cursor_filter(
            self._base_query(),
            sort_field="username",
            sort_direction=SortDirection.ASC,
            direction=PaginationDirection.NEXT,
            cursor_id=cursor_id,
            cursor_sort_value="alice",
        )
        where_clause = str(result.whereclause)
        assert "username" in where_clause.lower()

    def test_username_sort_backward_desc(self) -> None:
        cursor_id = uuid4()
        result = _apply_who_can_cursor_filter(
            self._base_query(),
            sort_field="username",
            sort_direction=SortDirection.DESC,
            direction=PaginationDirection.PREV,
            cursor_id=cursor_id,
            cursor_sort_value="bob",
        )
        where_clause = str(result.whereclause)
        assert "username" in where_clause.lower()

    def test_username_sort_forward_desc_hits_less_than_branch(self) -> None:
        cursor_id = uuid4()
        result = _apply_who_can_cursor_filter(
            self._base_query(),
            sort_field="username",
            sort_direction=SortDirection.DESC,
            direction=PaginationDirection.NEXT,
            cursor_id=cursor_id,
            cursor_sort_value="carol",
        )
        where_clause = str(result.whereclause)
        assert "username" in where_clause.lower()

    def test_username_sort_backward_asc_hits_less_than_branch(self) -> None:
        cursor_id = uuid4()
        result = _apply_who_can_cursor_filter(
            self._base_query(),
            sort_field="username",
            sort_direction=SortDirection.ASC,
            direction=PaginationDirection.PREV,
            cursor_id=cursor_id,
            cursor_sort_value="dan",
        )
        where_clause = str(result.whereclause)
        assert "username" in where_clause.lower()


# ---------------------------------------------------------------------------
# _build_page_cursors
# ---------------------------------------------------------------------------


class TestBuildPageCursors:
    """Tests for _build_page_cursors."""

    def _make_who_can_user(self, username: str = "user") -> WhoCanUser:
        return WhoCanUser(id=uuid4(), username=username)

    def test_empty_results_returns_none_none(self) -> None:
        next_c, prev_c = _build_page_cursors(
            [],
            direction=PaginationDirection.NEXT,
            has_more=False,
            cursor_id=None,
            sort_field="id",
            sort_direction=SortDirection.ASC,
        )
        assert next_c is None
        assert prev_c is None

    def test_first_page_with_more(self) -> None:
        results = [self._make_who_can_user("a"), self._make_who_can_user("b")]
        next_c, prev_c = _build_page_cursors(
            results,
            direction=PaginationDirection.NEXT,
            has_more=True,
            cursor_id=None,
            sort_field="id",
            sort_direction=SortDirection.ASC,
        )
        assert next_c is not None
        assert prev_c is None

    def test_middle_page_forward(self) -> None:
        results = [self._make_who_can_user("a"), self._make_who_can_user("b")]
        cursor_id = uuid4()
        next_c, prev_c = _build_page_cursors(
            results,
            direction=PaginationDirection.NEXT,
            has_more=True,
            cursor_id=cursor_id,
            sort_field="id",
            sort_direction=SortDirection.ASC,
        )
        assert next_c is not None
        assert prev_c is not None

    def test_last_page_forward(self) -> None:
        results = [self._make_who_can_user("a")]
        cursor_id = uuid4()
        next_c, prev_c = _build_page_cursors(
            results,
            direction=PaginationDirection.NEXT,
            has_more=False,
            cursor_id=cursor_id,
            sort_field="id",
            sort_direction=SortDirection.ASC,
        )
        assert next_c is None
        assert prev_c is not None

    def test_backward_with_more(self) -> None:
        results = [self._make_who_can_user("a"), self._make_who_can_user("b")]
        cursor_id = uuid4()
        next_c, prev_c = _build_page_cursors(
            results,
            direction=PaginationDirection.PREV,
            has_more=True,
            cursor_id=cursor_id,
            sort_field="id",
            sort_direction=SortDirection.ASC,
        )
        assert next_c is not None
        assert prev_c is not None

    def test_backward_no_more(self) -> None:
        results = [self._make_who_can_user("a")]
        cursor_id = uuid4()
        next_c, prev_c = _build_page_cursors(
            results,
            direction=PaginationDirection.PREV,
            has_more=False,
            cursor_id=cursor_id,
            sort_field="id",
            sort_direction=SortDirection.ASC,
        )
        assert next_c is not None
        assert prev_c is None

    def test_username_sort_encodes_sort_value(self) -> None:
        results = [self._make_who_can_user("alice")]
        next_c, _ = _build_page_cursors(
            results,
            direction=PaginationDirection.NEXT,
            has_more=True,
            cursor_id=None,
            sort_field="username",
            sort_direction=SortDirection.ASC,
        )
        assert next_c is not None


# ---------------------------------------------------------------------------
# _check_user_authorized
# ---------------------------------------------------------------------------


class TestCheckUserAuthorized:
    """Tests for _check_user_authorized."""

    @pytest.mark.asyncio
    async def test_returns_allowed_from_authorize(self) -> None:
        db = AsyncMock()
        evaluator = AsyncMock()
        user = MagicMock(spec=User)
        user.id = uuid4()
        user.labels = {}
        user.authz_metadata = {}
        body = WhoCanRequest(action="read", resource_type="workflow")

        mock_result = MagicMock()
        mock_result.allowed = True

        with patch("syntara.authz.router.authorize", return_value=mock_result) as mock_auth:
            result = await _check_user_authorized(db, evaluator, user, body, "proj")
            assert result is True
            mock_auth.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_returns_false_when_denied(self) -> None:
        db = AsyncMock()
        evaluator = AsyncMock()
        user = MagicMock(spec=User)
        user.id = uuid4()
        user.labels = {}
        user.authz_metadata = {}
        body = WhoCanRequest(action="delete", resource_type="project")

        mock_result = MagicMock()
        mock_result.allowed = False

        with patch("syntara.authz.router.authorize", return_value=mock_result):
            result = await _check_user_authorized(db, evaluator, user, body, "")
            assert result is False


# ---------------------------------------------------------------------------
# _check_batch_authorization
# ---------------------------------------------------------------------------


class TestCheckBatchAuthorization:
    """Tests for _check_batch_authorization."""

    def _make_user(self, username: str) -> MagicMock:
        user = MagicMock(spec=User)
        user.id = uuid4()
        user.username = username
        user.labels = {}
        user.authz_metadata = {}
        return user

    @pytest.mark.asyncio
    async def test_collects_authorized_users(self) -> None:
        db = AsyncMock()
        evaluator = AsyncMock()
        u1 = self._make_user("alice")
        u2 = self._make_user("bob")
        body = WhoCanRequest(action="read", resource_type="workflow")
        authorized: list[WhoCanUser] = []
        checked: set[UUID] = set()

        with patch("syntara.authz.router._check_user_authorized", side_effect=[True, False]):
            await _check_batch_authorization(db, evaluator, [u1, u2], body, "", authorized, checked, 10)

        assert len(authorized) == 1
        assert authorized[0].username == "alice"
        assert u1.id in checked
        assert u2.id in checked

    @pytest.mark.asyncio
    async def test_stops_at_target_count(self) -> None:
        db = AsyncMock()
        evaluator = AsyncMock()
        u1 = self._make_user("alice")
        u2 = self._make_user("bob")
        u3 = self._make_user("charlie")
        body = WhoCanRequest(action="read", resource_type="workflow")
        authorized: list[WhoCanUser] = []
        checked: set[UUID] = set()

        with patch("syntara.authz.router._check_user_authorized", return_value=True):
            await _check_batch_authorization(db, evaluator, [u1, u2, u3], body, "", authorized, checked, 2)

        assert len(authorized) == 2
        assert len(checked) == 2


# ---------------------------------------------------------------------------
# _count_batch_authorized
# ---------------------------------------------------------------------------


class TestCountBatchAuthorized:
    """Tests for _count_batch_authorized."""

    def _make_user(self) -> MagicMock:
        user = MagicMock(spec=User)
        user.id = uuid4()
        user.labels = {}
        user.authz_metadata = {}
        return user

    @pytest.mark.asyncio
    async def test_counts_authorized_users(self) -> None:
        db = AsyncMock()
        evaluator = AsyncMock()
        u1 = self._make_user()
        u2 = self._make_user()
        body = WhoCanRequest(action="read", resource_type="workflow")

        with patch("syntara.authz.router._check_user_authorized", side_effect=[True, False]):
            count, scanned, cap_exceeded = await _count_batch_authorized(
                db, evaluator, [u1, u2], body, "proj", set(), 0, 0
            )

        assert count == 1
        assert scanned == 2
        assert cap_exceeded is False

    @pytest.mark.asyncio
    async def test_skips_already_checked_users(self) -> None:
        db = AsyncMock()
        evaluator = AsyncMock()
        u1 = self._make_user()
        u2 = self._make_user()
        body = WhoCanRequest(action="read", resource_type="workflow")
        already_checked = {u1.id}

        with patch("syntara.authz.router._check_user_authorized", return_value=True) as mock_check:
            count, scanned, cap_exceeded = await _count_batch_authorized(
                db, evaluator, [u1, u2], body, "proj", already_checked, 0, 0
            )

        assert count == 1
        assert scanned == 2
        assert cap_exceeded is False
        mock_check.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_accumulates_from_initial_count(self) -> None:
        db = AsyncMock()
        evaluator = AsyncMock()
        u1 = self._make_user()
        body = WhoCanRequest(action="read", resource_type="workflow")

        with patch("syntara.authz.router._check_user_authorized", return_value=True):
            count, _scanned, cap_exceeded = await _count_batch_authorized(
                db, evaluator, [u1], body, "proj", set(), 5, 0
            )

        assert count == 6
        assert cap_exceeded is False

    @pytest.mark.asyncio
    async def test_returns_cap_exceeded_when_scan_limit_hit(self) -> None:
        db = AsyncMock()
        evaluator = AsyncMock()
        u1 = self._make_user()
        body = WhoCanRequest(action="read", resource_type="workflow")

        with patch("syntara.authz.router._log_scan_cap_exceeded") as mock_log:
            count, _scanned, cap_exceeded = await _count_batch_authorized(
                db, evaluator, [u1], body, "proj", set(), 3, 10_000
            )

        assert cap_exceeded is True
        assert count == 3
        mock_log.assert_called_once_with(3)

    @pytest.mark.asyncio
    async def test_empty_batch_returns_unchanged(self) -> None:
        db = AsyncMock()
        evaluator = AsyncMock()
        body = WhoCanRequest(action="read", resource_type="workflow")

        count, scanned, cap_exceeded = await _count_batch_authorized(db, evaluator, [], body, "proj", set(), 2, 5)

        assert count == 2
        assert scanned == 5
        assert cap_exceeded is False
