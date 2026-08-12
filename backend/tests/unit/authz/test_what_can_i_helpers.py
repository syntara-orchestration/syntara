"""Unit tests for what_can_i helper functions in syntara.authz.router."""

import pytest

from syntara.authz.router import (
    PermissionEntry,
    WhatCanIResponse,
    _is_cursor_stale,
    _paginate_in_memory,
)
from syntara.core.exceptions import SafeValueError
from syntara.core.utils.cursor import (
    CursorData,
    SortDirection,
)


def _make_permission(
    policy_name: str = "policy",
    effect: str = "allow",
    scope: str = "any",
    project: str = "",
) -> PermissionEntry:
    return PermissionEntry(
        policy_name=policy_name,
        effect=effect,
        actions=["read"],
        scope=scope,
        project=project,
    )


def _sample_permissions() -> list[PermissionEntry]:
    """Build a deterministic set of permissions for testing."""
    return [
        _make_permission(policy_name="charlie:read:any", effect="allow", scope="any"),
        _make_permission(policy_name="alpha:read:any", effect="allow", scope="any"),
        _make_permission(policy_name="bravo:create:any", effect="deny", scope="project", project="proj-a"),
        _make_permission(policy_name="delta:update:self", effect="allow", scope="self"),
        _make_permission(policy_name="echo:delete:any", effect="deny", scope="any"),
    ]


# ---------------------------------------------------------------------------
# _is_cursor_stale
# ---------------------------------------------------------------------------


class TestIsCursorStale:
    """Tests for _is_cursor_stale detection."""

    def test_none_index_is_not_stale(self) -> None:
        items = _sample_permissions()
        assert _is_cursor_stale(CursorData(), None, items, "policy_name") is False

    def test_valid_index_matching_value_is_not_stale(self) -> None:
        items = _sample_permissions()
        sorted_items = sorted(items, key=lambda p: p.policy_name)
        cursor_data = CursorData(created_at=sorted_items[0].policy_name)
        assert _is_cursor_stale(cursor_data, 0, sorted_items, "policy_name") is False

    def test_valid_index_mismatched_value_is_stale(self) -> None:
        items = _sample_permissions()
        sorted_items = sorted(items, key=lambda p: p.policy_name)
        cursor_data = CursorData(created_at="nonexistent:policy:name")
        assert _is_cursor_stale(cursor_data, 0, sorted_items, "policy_name") is True

    def test_out_of_bounds_index_is_stale(self) -> None:
        items = _sample_permissions()
        cursor_data = CursorData(created_at="anything")
        assert _is_cursor_stale(cursor_data, 100, items, "policy_name") is True

    def test_negative_index_is_stale(self) -> None:
        items = _sample_permissions()
        cursor_data = CursorData(created_at="anything")
        assert _is_cursor_stale(cursor_data, -1, items, "policy_name") is True

    def test_missing_created_at_in_cursor_data_is_not_stale(self) -> None:
        items = _sample_permissions()
        assert _is_cursor_stale(CursorData(), 0, items, "policy_name") is False


# ---------------------------------------------------------------------------
# _paginate_in_memory — staleness detection (end-to-end through paginator)
# ---------------------------------------------------------------------------


class TestPaginateInMemoryStale:
    """Tests that stale or out-of-range cursors reset pagination to page 1."""

    def test_staleness_detected_resets_to_page_one(self) -> None:
        items = _sample_permissions()
        page1 = _paginate_in_memory(
            items=items,
            sort_field="policy_name",
            sort_direction=SortDirection.ASC,
            limit=2,
            cursor=None,
            include_total=False,
        )
        modified = [_make_permission(policy_name="aaa:new"), *items]
        result = _paginate_in_memory(
            items=modified,
            sort_field="policy_name",
            sort_direction=SortDirection.ASC,
            limit=2,
            cursor=page1.next,
            include_total=False,
        )
        assert result.prev is None
        assert result.resources[0].policy_name == "aaa:new"

    def test_out_of_range_cursor_resets_to_page_one(self) -> None:
        large_items = _sample_permissions() * 4
        big_result = _paginate_in_memory(
            items=large_items,
            sort_field="policy_name",
            sort_direction=SortDirection.ASC,
            limit=2,
            cursor=None,
            include_total=False,
        )
        tiny_items = _sample_permissions()[:2]
        result = _paginate_in_memory(
            items=tiny_items,
            sort_field="policy_name",
            sort_direction=SortDirection.ASC,
            limit=2,
            cursor=big_result.next,
            include_total=False,
        )
        assert result.resources != []
        assert result.prev is None


# ---------------------------------------------------------------------------
# _paginate_in_memory — malformed cursor handling
# ---------------------------------------------------------------------------


class TestPaginateInMemoryMalformedCursor:
    """Tests that malformed cursor strings raise SafeValueError (→ 422 at the API layer)."""

    def test_non_base64_cursor_raises(self) -> None:
        items = _sample_permissions()
        with pytest.raises(SafeValueError):
            _paginate_in_memory(
                items=items,
                sort_field="policy_name",
                sort_direction=SortDirection.ASC,
                limit=20,
                cursor="not-valid-base64!!!",
                include_total=False,
            )

    def test_base64_but_not_json_cursor_raises(self) -> None:
        import base64
        import json

        cursor = base64.b64encode(b"this is not json").decode()
        items = _sample_permissions()
        with pytest.raises(json.JSONDecodeError):
            _paginate_in_memory(
                items=items,
                sort_field="policy_name",
                sort_direction=SortDirection.ASC,
                limit=20,
                cursor=cursor,
                include_total=False,
            )

    def test_empty_string_cursor_returns_first_page(self) -> None:
        """Empty string is falsy, so it's treated as no cursor (returns page 1)."""
        items = _sample_permissions()
        result = _paginate_in_memory(
            items=items,
            sort_field="policy_name",
            sort_direction=SortDirection.ASC,
            limit=20,
            cursor="",
            include_total=False,
        )
        assert len(result.resources) == len(items)
        assert result.prev is None


# ---------------------------------------------------------------------------
# _paginate_in_memory — basic behavior
# ---------------------------------------------------------------------------


class TestPaginateInMemoryBasic:
    """Tests for _paginate_in_memory basic pagination."""

    def test_empty_list_returns_empty_resources(self) -> None:
        result = _paginate_in_memory(
            items=[],
            sort_field="policy_name",
            sort_direction=SortDirection.ASC,
            limit=20,
            cursor=None,
            include_total=False,
        )
        assert isinstance(result, WhatCanIResponse)
        assert result.resources == []
        assert result.next is None
        assert result.prev is None
        assert result.total is None

    def test_single_page_returns_all_items(self) -> None:
        items = _sample_permissions()
        result = _paginate_in_memory(
            items=items,
            sort_field="policy_name",
            sort_direction=SortDirection.ASC,
            limit=100,
            cursor=None,
            include_total=False,
        )
        assert len(result.resources) == len(items)
        assert result.next is None
        assert result.prev is None

    def test_single_page_sorted_ascending(self) -> None:
        items = _sample_permissions()
        result = _paginate_in_memory(
            items=items,
            sort_field="policy_name",
            sort_direction=SortDirection.ASC,
            limit=100,
            cursor=None,
            include_total=False,
        )
        names = [p.policy_name for p in result.resources]
        assert names == sorted(names)

    def test_single_page_sorted_descending(self) -> None:
        items = _sample_permissions()
        result = _paginate_in_memory(
            items=items,
            sort_field="policy_name",
            sort_direction=SortDirection.DESC,
            limit=100,
            cursor=None,
            include_total=False,
        )
        names = [p.policy_name for p in result.resources]
        assert names == sorted(names, reverse=True)

    def test_sort_by_effect(self) -> None:
        items = _sample_permissions()
        result = _paginate_in_memory(
            items=items,
            sort_field="effect",
            sort_direction=SortDirection.ASC,
            limit=100,
            cursor=None,
            include_total=False,
        )
        effects = [p.effect for p in result.resources]
        assert effects == sorted(effects)

    def test_sort_by_scope(self) -> None:
        items = _sample_permissions()
        result = _paginate_in_memory(
            items=items,
            sort_field="scope",
            sort_direction=SortDirection.ASC,
            limit=100,
            cursor=None,
            include_total=False,
        )
        scopes = [p.scope for p in result.resources]
        assert scopes == sorted(scopes)

    def test_sort_stability_with_duplicate_values(self) -> None:
        """Duplicate sort field values must produce a deterministic order via the tiebreaker tuple."""
        items = [
            _make_permission(policy_name="z:write:any", effect="allow", scope="any"),
            _make_permission(policy_name="a:read:any", effect="allow", scope="any"),
            _make_permission(policy_name="m:delete:any", effect="allow", scope="any"),
        ]
        result1 = _paginate_in_memory(
            items=items,
            sort_field="effect",
            sort_direction=SortDirection.ASC,
            limit=100,
            cursor=None,
            include_total=False,
        )
        result2 = _paginate_in_memory(
            items=items,
            sort_field="effect",
            sort_direction=SortDirection.ASC,
            limit=100,
            cursor=None,
            include_total=False,
        )
        names1 = [p.policy_name for p in result1.resources]
        names2 = [p.policy_name for p in result2.resources]
        assert names1 == names2
        assert names1 == ["a:read:any", "m:delete:any", "z:write:any"]

    def test_duplicate_sort_field_pagination_stability(self) -> None:
        """Paginating through items with identical sort values must not skip or duplicate items."""
        items = [_make_permission(policy_name=f"policy-{i}:read:any", effect="allow", scope="any") for i in range(5)]
        all_names: list[str] = []
        cursor = None
        for _ in range(10):
            result = _paginate_in_memory(
                items=items,
                sort_field="effect",
                sort_direction=SortDirection.ASC,
                limit=2,
                cursor=cursor,
                include_total=False,
            )
            all_names.extend(p.policy_name for p in result.resources)
            if result.next is None:
                break
            cursor = result.next
        assert sorted(all_names) == sorted(p.policy_name for p in items)
        assert len(all_names) == len(set(all_names))


# ---------------------------------------------------------------------------
# _paginate_in_memory — include_total
# ---------------------------------------------------------------------------


class TestPaginateInMemoryTotal:
    """Tests for include_total behavior."""

    def test_include_total_false_returns_none(self) -> None:
        result = _paginate_in_memory(
            items=_sample_permissions(),
            sort_field="policy_name",
            sort_direction=SortDirection.ASC,
            limit=100,
            cursor=None,
            include_total=False,
        )
        assert result.total is None

    def test_include_total_true_returns_count(self) -> None:
        items = _sample_permissions()
        result = _paginate_in_memory(
            items=items,
            sort_field="policy_name",
            sort_direction=SortDirection.ASC,
            limit=100,
            cursor=None,
            include_total=True,
        )
        assert result.total == len(items)

    def test_include_total_with_pagination(self) -> None:
        items = _sample_permissions()
        result = _paginate_in_memory(
            items=items,
            sort_field="policy_name",
            sort_direction=SortDirection.ASC,
            limit=2,
            cursor=None,
            include_total=True,
        )
        assert result.total == len(items)
        assert len(result.resources) == 2


# ---------------------------------------------------------------------------
# _paginate_in_memory — multi-page traversal
# ---------------------------------------------------------------------------


class TestPaginateInMemoryMultiPage:
    """Tests for cursor-based pagination across multiple pages."""

    def test_first_page_has_next_no_prev(self) -> None:
        items = _sample_permissions()
        result = _paginate_in_memory(
            items=items,
            sort_field="policy_name",
            sort_direction=SortDirection.ASC,
            limit=2,
            cursor=None,
            include_total=False,
        )
        assert len(result.resources) == 2
        assert result.next is not None
        assert result.prev is None

    def test_second_page_has_both_cursors(self) -> None:
        items = _sample_permissions()
        page1 = _paginate_in_memory(
            items=items,
            sort_field="policy_name",
            sort_direction=SortDirection.ASC,
            limit=2,
            cursor=None,
            include_total=False,
        )
        page2 = _paginate_in_memory(
            items=items,
            sort_field="policy_name",
            sort_direction=SortDirection.ASC,
            limit=2,
            cursor=page1.next,
            include_total=False,
        )
        assert len(page2.resources) == 2
        assert page2.next is not None  # Still more items
        assert page2.prev is not None

    def test_last_page_has_prev_no_next(self) -> None:
        items = _sample_permissions()
        page1 = _paginate_in_memory(
            items=items,
            sort_field="policy_name",
            sort_direction=SortDirection.ASC,
            limit=2,
            cursor=None,
            include_total=False,
        )
        page2 = _paginate_in_memory(
            items=items,
            sort_field="policy_name",
            sort_direction=SortDirection.ASC,
            limit=2,
            cursor=page1.next,
            include_total=False,
        )
        page3 = _paginate_in_memory(
            items=items,
            sort_field="policy_name",
            sort_direction=SortDirection.ASC,
            limit=2,
            cursor=page2.next,
            include_total=False,
        )
        assert len(page3.resources) == 1  # 5 items total, page3 gets the last one
        assert page3.next is None
        assert page3.prev is not None

    def test_no_overlap_between_pages(self) -> None:
        items = _sample_permissions()
        page1 = _paginate_in_memory(
            items=items,
            sort_field="policy_name",
            sort_direction=SortDirection.ASC,
            limit=2,
            cursor=None,
            include_total=False,
        )
        page2 = _paginate_in_memory(
            items=items,
            sort_field="policy_name",
            sort_direction=SortDirection.ASC,
            limit=2,
            cursor=page1.next,
            include_total=False,
        )
        page1_names = {p.policy_name for p in page1.resources}
        page2_names = {p.policy_name for p in page2.resources}
        assert page1_names.isdisjoint(page2_names)

    def test_all_items_covered_across_pages(self) -> None:
        items = _sample_permissions()
        all_names: list[str] = []
        cursor = None
        for _ in range(10):  # Safety limit
            result = _paginate_in_memory(
                items=items,
                sort_field="policy_name",
                sort_direction=SortDirection.ASC,
                limit=2,
                cursor=cursor,
                include_total=False,
            )
            all_names.extend(p.policy_name for p in result.resources)
            if result.next is None:
                break
            cursor = result.next
        assert sorted(all_names) == sorted(p.policy_name for p in items)

    def test_backward_navigation_returns_previous_page(self) -> None:
        items = _sample_permissions()
        page1 = _paginate_in_memory(
            items=items,
            sort_field="policy_name",
            sort_direction=SortDirection.ASC,
            limit=2,
            cursor=None,
            include_total=False,
        )
        page1_names = [p.policy_name for p in page1.resources]

        page2 = _paginate_in_memory(
            items=items,
            sort_field="policy_name",
            sort_direction=SortDirection.ASC,
            limit=2,
            cursor=page1.next,
            include_total=False,
        )

        back_page = _paginate_in_memory(
            items=items,
            sort_field="policy_name",
            sort_direction=SortDirection.ASC,
            limit=2,
            cursor=page2.prev,
            include_total=False,
        )
        back_names = [p.policy_name for p in back_page.resources]
        assert back_names == page1_names

    def test_descending_sort_pagination(self) -> None:
        items = _sample_permissions()
        all_names: list[str] = []
        cursor = None
        for _ in range(10):
            result = _paginate_in_memory(
                items=items,
                sort_field="policy_name",
                sort_direction=SortDirection.DESC,
                limit=2,
                cursor=cursor,
                include_total=False,
            )
            all_names.extend(p.policy_name for p in result.resources)
            if result.next is None:
                break
            cursor = result.next
        assert all_names == sorted(all_names, reverse=True)
