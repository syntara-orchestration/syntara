"""Unit tests for who_can helper functions in syntara.authz.router."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Select
from sqlmodel import select

from syntara.authz.exceptions import AuthorizationDeniedError
from syntara.authz.router import (
    _WHO_CAN_GATE_RULES,
    WhoCanRequest,
    WhoCanUser,
    _apply_who_can_cursor_filter,
    _build_page_cursors,
    _can_edit_workflow_in_project,
    _check_batch_authorization,
    _check_user_authorized,
    _count_batch_authorized,
    _enforce_who_can_permission,
    _user_has_authz_query_permission,
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

    @pytest.mark.asyncio
    async def test_passes_stripped_labels_to_authorize(self) -> None:
        """Tier 1 callers have labels/metadata stripped at the endpoint level.

        Simulate the who_can endpoint flow: _enforce_who_can_permission returns
        is_trusted=False for Tier 1, so the endpoint creates a sanitized copy
        of the body (via model_copy) before passing it to _check_user_authorized.
        """
        db = AsyncMock()
        evaluator = AsyncMock()
        user = MagicMock(spec=User)
        user.id = uuid4()
        user.labels = {}
        user.authz_metadata = {}
        original_body = WhoCanRequest(
            action="decide",
            resource_type="approval",
            resource_labels={"forged": "true"},
            resource_metadata={"admin": True},
        )

        # Simulate the endpoint's model_copy stripping for non-trusted callers
        sanitized_body = original_body.model_copy(update={"resource_labels": {}, "resource_metadata": {}})

        # Original is untouched
        assert original_body.resource_labels == {"forged": "true"}

        mock_result = MagicMock()
        mock_result.allowed = True

        with patch("syntara.authz.router.authorize", return_value=mock_result) as mock_auth:
            await _check_user_authorized(db, evaluator, user, sanitized_body, "my-project")
            authz_req = mock_auth.call_args[0][2]
            assert authz_req.resource_labels == {}
            assert authz_req.resource_metadata == {}


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


# ---------------------------------------------------------------------------
# _user_has_authz_query_permission
# ---------------------------------------------------------------------------


class TestUserHasAuthzQueryPermission:
    """Tests for _user_has_authz_query_permission."""

    def _make_user(self) -> MagicMock:
        user = MagicMock(spec=User)
        user.id = uuid4()
        user.labels = {}
        user.authz_metadata = {}
        return user

    @pytest.mark.asyncio
    async def test_returns_true_when_authorized(self) -> None:
        db = AsyncMock()
        evaluator = AsyncMock()
        user = self._make_user()

        mock_result = MagicMock()
        mock_result.allowed = True

        with patch("syntara.authz.router.authorize", return_value=mock_result) as mock_auth:
            result = await _user_has_authz_query_permission(user, evaluator, db)
            assert result is True
            mock_auth.assert_awaited_once()
            call_args = mock_auth.call_args
            authz_request = call_args[0][2]
            assert authz_request.action == "query"
            assert authz_request.resource_type == "authz"

    @pytest.mark.asyncio
    async def test_returns_false_when_denied(self) -> None:
        db = AsyncMock()
        evaluator = AsyncMock()
        user = self._make_user()

        mock_result = MagicMock()
        mock_result.allowed = False

        with patch("syntara.authz.router.authorize", return_value=mock_result):
            result = await _user_has_authz_query_permission(user, evaluator, db)
            assert result is False


# ---------------------------------------------------------------------------
# who_can two-tier permission gate
# ---------------------------------------------------------------------------


class TestCanEditWorkflowInProject:
    """Tests for _can_edit_workflow_in_project."""

    def _make_user(self) -> MagicMock:
        user = MagicMock(spec=User)
        user.id = uuid4()
        user.labels = {}
        user.authz_metadata = {}
        return user

    @pytest.mark.asyncio
    async def test_returns_true_when_user_can_update(self) -> None:
        db = AsyncMock()
        evaluator = AsyncMock()
        user = self._make_user()

        mock_result = MagicMock()
        mock_result.allowed = True

        with patch("syntara.authz.router.authorize", return_value=mock_result) as mock_auth:
            result = await _can_edit_workflow_in_project(user, evaluator, db, "proj-1")
            assert result is True
            call_args = mock_auth.call_args[0][2]
            assert call_args.action == "update"
            assert call_args.resource_type == "workflow"
            assert call_args.resource_project == "proj-1"

    @pytest.mark.asyncio
    async def test_returns_true_when_user_can_create(self) -> None:
        db = AsyncMock()
        evaluator = AsyncMock()
        user = self._make_user()

        denied = MagicMock()
        denied.allowed = False
        allowed = MagicMock()
        allowed.allowed = True

        with patch("syntara.authz.router.authorize", side_effect=[denied, allowed]) as mock_auth:
            result = await _can_edit_workflow_in_project(user, evaluator, db, "proj-1")
            assert result is True
            assert mock_auth.await_count == 2
            assert mock_auth.call_args_list[1][0][2].action == "create"

    @pytest.mark.asyncio
    async def test_returns_false_when_neither_update_nor_create(self) -> None:
        db = AsyncMock()
        evaluator = AsyncMock()
        user = self._make_user()

        denied = MagicMock()
        denied.allowed = False

        with patch("syntara.authz.router.authorize", return_value=denied):
            result = await _can_edit_workflow_in_project(user, evaluator, db, "proj-1")
            assert result is False


class TestWhoCanPermissionGate:
    """Tests for the two-tier authorization gate in _enforce_who_can_permission."""

    def _make_user(self) -> MagicMock:
        user = MagicMock(spec=User)
        user.id = uuid4()
        user.labels = {}
        user.authz_metadata = {}
        return user

    def _make_request(self, *, cert_authenticated: bool = False) -> MagicMock:
        request = MagicMock()
        request.state.is_cert_authenticated = cert_authenticated
        return request

    @pytest.mark.asyncio
    async def test_rejects_disallowed_action_type_pair(self) -> None:
        db = AsyncMock()
        evaluator = AsyncMock()
        user = self._make_user()
        body = WhoCanRequest(
            action="delete",
            resource_type="project",
            resource_project="my-project",
        )

        with (
            patch("syntara.authz.router._user_has_authz_query_permission", return_value=False),
            patch("syntara.authz.router._dispatch_who_can_denied"),
            pytest.raises(
                AuthorizationDeniedError,
                match="who_can query for project:delete is not permitted for non-admin users",
            ),
        ):
            await _enforce_who_can_permission(
                body, user, db, evaluator, resource_project="my-project", request=self._make_request()
            )

    def test_gate_rules_contain_approval_decide(self) -> None:
        pairs = {(r.resource_type, r.action) for r in _WHO_CAN_GATE_RULES}
        assert ("approval", "decide") in pairs

    @pytest.mark.asyncio
    async def test_tier1_allows_workflow_editor_with_project(self) -> None:
        db = AsyncMock()
        evaluator = AsyncMock()
        user = self._make_user()
        body = WhoCanRequest(
            action="decide",
            resource_type="approval",
            resource_project="my-project",
        )

        mock_result = MagicMock()
        mock_result.allowed = True

        with (
            patch("syntara.authz.router._user_has_authz_query_permission", return_value=False),
            patch("syntara.authz.router.authorize", return_value=mock_result),
        ):
            is_trusted = await _enforce_who_can_permission(
                body, user, db, evaluator, resource_project="my-project", request=self._make_request()
            )
            assert is_trusted is False

    @pytest.mark.asyncio
    async def test_tier1_denies_non_editor_with_project(self) -> None:
        db = AsyncMock()
        evaluator = AsyncMock()
        user = self._make_user()
        body = WhoCanRequest(
            action="decide",
            resource_type="approval",
            resource_project="my-project",
        )

        mock_result = MagicMock()
        mock_result.allowed = False

        with (
            patch("syntara.authz.router._user_has_authz_query_permission", return_value=False),
            patch("syntara.authz.router.authorize", return_value=mock_result),
            patch("syntara.authz.router._dispatch_who_can_denied"),
            pytest.raises(AuthorizationDeniedError, match="Not authorized to query approval in project my-project"),
        ):
            await _enforce_who_can_permission(
                body, user, db, evaluator, resource_project="my-project", request=self._make_request()
            )

    @pytest.mark.asyncio
    async def test_tier1_resource_project_drives_check_not_resource_id(self) -> None:
        """resource_project is what drives Tier 1; resource_id is informational only."""
        db = AsyncMock()
        evaluator = AsyncMock()
        user = self._make_user()
        body = WhoCanRequest(
            action="decide",
            resource_type="approval",
            resource_id="res-123",
        )

        mock_result = MagicMock()
        mock_result.allowed = True

        with (
            patch("syntara.authz.router._user_has_authz_query_permission", return_value=False),
            patch("syntara.authz.router.authorize", return_value=mock_result) as mock_auth,
        ):
            await _enforce_who_can_permission(
                body, user, db, evaluator, resource_project="my-project", request=self._make_request()
            )
            mock_auth.assert_awaited()
            authz_req = mock_auth.call_args[0][2]
            assert authz_req.resource_type == "workflow"
            assert authz_req.action in ("update", "create")

    @pytest.mark.asyncio
    async def test_resource_id_alone_without_project_is_denied(self) -> None:
        """resource_id without resource_project falls to Tier 2, not Tier 1."""
        db = AsyncMock()
        evaluator = AsyncMock()
        user = self._make_user()
        body = WhoCanRequest(
            action="decide",
            resource_type="approval",
            resource_id="res-123",
        )

        with (
            patch("syntara.authz.router._user_has_authz_query_permission", return_value=False),
            patch("syntara.authz.router._dispatch_who_can_denied"),
            pytest.raises(AuthorizationDeniedError, match="System-wide who_can queries require authz:query permission"),
        ):
            await _enforce_who_can_permission(
                body, user, db, evaluator, resource_project="", request=self._make_request()
            )

    @pytest.mark.asyncio
    async def test_tier1_does_not_use_client_labels(self) -> None:
        """Client-supplied labels/metadata must not influence the gate."""
        db = AsyncMock()
        evaluator = AsyncMock()
        user = self._make_user()
        body = WhoCanRequest(
            action="decide",
            resource_type="approval",
            resource_project="my-project",
            resource_labels={"forged": "true"},
            resource_metadata={"admin": True},
        )

        mock_result = MagicMock()
        mock_result.allowed = True

        with (
            patch("syntara.authz.router._user_has_authz_query_permission", return_value=False),
            patch("syntara.authz.router.authorize", return_value=mock_result) as mock_auth,
        ):
            is_trusted = await _enforce_who_can_permission(
                body, user, db, evaluator, resource_project="my-project", request=self._make_request()
            )
            assert is_trusted is False
            authz_req = mock_auth.call_args[0][2]
            assert authz_req.resource_labels == {}
            assert authz_req.resource_metadata == {}

    @pytest.mark.asyncio
    async def test_authz_query_allows_scoped_unlisted_pair(self) -> None:
        """Admin with authz:query can query any scoped (resource_type, action) pair."""
        db = AsyncMock()
        evaluator = AsyncMock()
        user = self._make_user()
        body = WhoCanRequest(
            action="assign",
            resource_type="role-assignment",
            resource_project="my-project",
        )

        with patch("syntara.authz.router._user_has_authz_query_permission", return_value=True):
            is_trusted = await _enforce_who_can_permission(
                body, user, db, evaluator, resource_project="my-project", request=self._make_request()
            )
            assert is_trusted is True

    @pytest.mark.asyncio
    async def test_tier2_allows_admin_without_project(self) -> None:
        db = AsyncMock()
        evaluator = AsyncMock()
        user = self._make_user()
        body = WhoCanRequest(
            action="decide",
            resource_type="approval",
        )

        with patch("syntara.authz.router._user_has_authz_query_permission", return_value=True):
            is_trusted = await _enforce_who_can_permission(
                body, user, db, evaluator, resource_project="", request=self._make_request()
            )
            assert is_trusted is True

    @pytest.mark.asyncio
    async def test_tier2_denies_non_admin_without_project(self) -> None:
        db = AsyncMock()
        evaluator = AsyncMock()
        user = self._make_user()
        body = WhoCanRequest(
            action="decide",
            resource_type="approval",
        )

        with (
            patch("syntara.authz.router._user_has_authz_query_permission", return_value=False),
            patch("syntara.authz.router._dispatch_who_can_denied"),
            pytest.raises(AuthorizationDeniedError, match="System-wide who_can queries require authz:query permission"),
        ):
            await _enforce_who_can_permission(
                body, user, db, evaluator, resource_project="", request=self._make_request()
            )

    @pytest.mark.asyncio
    async def test_cert_authenticated_bypasses_gate(self) -> None:
        """Certificate-authenticated requests bypass the permission gate entirely."""
        db = AsyncMock()
        evaluator = AsyncMock()
        user = self._make_user()
        body = WhoCanRequest(
            action="delete",
            resource_type="project",
            resource_project="my-project",
        )

        is_trusted = await _enforce_who_can_permission(
            body,
            user,
            db,
            evaluator,
            resource_project="my-project",
            request=self._make_request(cert_authenticated=True),
        )
        assert is_trusted is True

    @pytest.mark.asyncio
    async def test_tier1_forged_labels_stripped_before_batch_auth(self) -> None:
        """End-to-end: Tier 1 gate + model_copy + batch auth receives empty labels."""
        db = AsyncMock()
        evaluator = AsyncMock()
        user = self._make_user()
        body = WhoCanRequest(
            action="decide",
            resource_type="approval",
            resource_project="my-project",
            resource_labels={"forged": "true"},
            resource_metadata={"admin": True},
        )

        gate_result = MagicMock()
        gate_result.allowed = True

        with (
            patch("syntara.authz.router._user_has_authz_query_permission", return_value=False),
            patch("syntara.authz.router.authorize", return_value=gate_result),
        ):
            is_trusted = await _enforce_who_can_permission(
                body, user, db, evaluator, resource_project="my-project", request=self._make_request()
            )
        assert is_trusted is False

        # Replicate the endpoint's model_copy stripping
        sanitized = body.model_copy(update={"resource_labels": {}, "resource_metadata": {}})
        assert body.resource_labels == {"forged": "true"}  # original untouched

        # Verify batch authorization receives the stripped body
        alice = self._make_user()
        alice.username = "alice"
        authorized: list[WhoCanUser] = []
        checked: set[UUID] = set()

        scan_result = MagicMock()
        scan_result.allowed = True
        with patch("syntara.authz.router.authorize", return_value=scan_result) as mock_auth:
            await _check_batch_authorization(db, evaluator, [alice], sanitized, "my-project", authorized, checked, 10)
            authz_req = mock_auth.call_args[0][2]
            assert authz_req.resource_labels == {}
            assert authz_req.resource_metadata == {}
