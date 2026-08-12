"""Tests for role/policy listing with builtin+DB merging, pagination, filtering, and sorting.

These tests exercise the _list_with_builtins / _builtins_first_page /
_builtins_last_page logic that merges in-memory builtin resources with
database resources into a single paginated response.
"""

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.authz.role_conventions import BUILTIN_POLICIES, BUILTIN_ROLES
from syntara.authz.services.policy_service import PolicyService
from syntara.authz.services.role_service import RoleService
from syntara.core.models import User

_P_READ = "workflow:read:any"
_P_WRITE = "workflow:create:any"

_STMT = [{"effect": "allow", "actions": ["workflow:read"], "scope": "any"}]

SYSTEM_BUILTIN_ROLES = [r for r in BUILTIN_ROLES if r.scope == "system"]
PROJECT_BUILTIN_ROLES = [r for r in BUILTIN_ROLES if r.scope == "project"]
ALL_BUILTIN_ROLE_COUNT = len(BUILTIN_ROLES)

SYSTEM_BUILTIN_POLICIES = [p for p in BUILTIN_POLICIES if p.scope != "project"]
PROJECT_BUILTIN_POLICIES = [p for p in BUILTIN_POLICIES if p.scope == "project"]
ALL_BUILTIN_POLICY_COUNT = len(BUILTIN_POLICIES)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _all_names(result) -> list[str]:
    return [r.name for r in result.resources]


async def _create_db_roles(
    svc: RoleService,
    count: int,
    prefix: str = "db-role",
) -> list[str]:
    names = []
    for i in range(count):
        name = f"{prefix}-{i:03d}"
        await svc.create_role(name=name, policies=[_P_READ])
        names.append(name)
    return names


async def _create_db_policies(
    svc: PolicyService,
    count: int,
    prefix: str = "db-policy",
) -> list[str]:
    names = []
    for i in range(count):
        name = f"{prefix}-{i:03d}"
        await svc.create_policy(name=name, statements=_STMT)
        names.append(name)
    return names


# ============================================================================
# Role listing — basic
# ============================================================================


@pytest.mark.asyncio
async def test_list_roles_includes_all_builtins(test_db_session: AsyncSession, test_user: User) -> None:
    """All builtin roles appear in the listing (with a large enough limit)."""
    svc = RoleService(test_db_session, test_user)
    result = await svc.list_roles(limit=200)
    names = _all_names(result)
    for r in BUILTIN_ROLES:
        assert r.name in names, f"Builtin role '{r.name}' missing from listing"


@pytest.mark.asyncio
async def test_list_roles_includes_db_roles(test_db_session: AsyncSession, test_user: User) -> None:
    """Custom DB roles appear alongside builtins."""
    svc = RoleService(test_db_session, test_user)
    db_names = await _create_db_roles(svc, 3)
    result = await svc.list_roles(limit=200)
    names = _all_names(result)
    for n in db_names:
        assert n in names
    assert len(result.resources) == ALL_BUILTIN_ROLE_COUNT + 3


@pytest.mark.asyncio
async def test_list_roles_total_count(test_db_session: AsyncSession, test_user: User) -> None:
    """include_total returns correct total including builtins and DB items."""
    svc = RoleService(test_db_session, test_user)
    await _create_db_roles(svc, 5)
    result = await svc.list_roles(limit=200, include_total=True)
    assert result.total == ALL_BUILTIN_ROLE_COUNT + 5


# ============================================================================
# Role listing — is_builtin filter
# ============================================================================


@pytest.mark.asyncio
async def test_list_roles_filter_is_builtin_false(test_db_session: AsyncSession, test_user: User) -> None:
    """is_builtin=false should return DB roles plus any BUILTIN_ROLES entries with is_builtin=False."""
    svc = RoleService(test_db_session, test_user)
    await _create_db_roles(svc, 3)
    non_builtin_builtins = [r for r in BUILTIN_ROLES if not r.is_builtin]
    result = await svc.list_roles(
        limit=200,
        query_params_items=[("is_builtin", "false")],
    )
    names = _all_names(result)
    assert len(names) == 3 + len(non_builtin_builtins)
    for r in result.resources:
        assert r.is_builtin is False


@pytest.mark.asyncio
async def test_list_roles_filter_is_builtin_true(test_db_session: AsyncSession, test_user: User) -> None:
    """is_builtin=true should return only roles where is_builtin=True.

    The 'default' role (in BUILTIN_ROLES but with is_builtin=False) should
    NOT appear when filtering for is_builtin=true.
    """
    svc = RoleService(test_db_session, test_user)
    await _create_db_roles(svc, 3)
    result = await svc.list_roles(
        limit=200,
        query_params_items=[("is_builtin", "true")],
    )
    for r in result.resources:
        assert r.is_builtin is True, (
            f"Role '{r.name}' has is_builtin={r.is_builtin} but appeared in is_builtin=true results"
        )


@pytest.mark.asyncio
async def test_list_roles_authenticated_role_is_builtin(test_db_session: AsyncSession, test_user: User) -> None:
    """The 'authenticated' role (is_builtin=True) should appear for is_builtin=true."""
    svc = RoleService(test_db_session, test_user)
    result = await svc.list_roles(
        limit=200,
        query_params_items=[("is_builtin", "true")],
    )
    names = _all_names(result)
    assert "authenticated" in names


# ============================================================================
# Role listing — name / scope filters
# ============================================================================


@pytest.mark.asyncio
async def test_list_roles_filter_name_exact(test_db_session: AsyncSession, test_user: User) -> None:
    """Exact name filter returns only the matching role."""
    svc = RoleService(test_db_session, test_user)
    await _create_db_roles(svc, 3)
    result = await svc.list_roles(
        limit=200,
        query_params_items=[("name", "admin")],
    )
    names = _all_names(result)
    assert names == ["admin"]


@pytest.mark.asyncio
async def test_list_roles_filter_name_contains(test_db_session: AsyncSession, test_user: User) -> None:
    """name[contains] filter matches both builtins and DB roles."""
    svc = RoleService(test_db_session, test_user)
    await _create_db_roles(svc, 3, prefix="admin-custom")
    result = await svc.list_roles(
        limit=200,
        query_params_items=[("name[contains]", "admin")],
    )
    names = _all_names(result)
    assert "admin" in names
    assert "project-admin" in names
    for n in names:
        assert "admin" in n.lower()


@pytest.mark.asyncio
async def test_list_roles_filter_scope_system(test_db_session: AsyncSession, test_user: User) -> None:
    """scope=system returns only system-scoped roles."""
    svc = RoleService(test_db_session, test_user)
    result = await svc.list_roles(
        limit=200,
        query_params_items=[("scope", "system")],
    )
    for r in result.resources:
        assert r.scope == "system", f"Role '{r.name}' has scope '{r.scope}'"


@pytest.mark.asyncio
async def test_list_roles_filter_scope_project(test_db_session: AsyncSession, test_user: User) -> None:
    """scope=project returns only project-scoped roles."""
    svc = RoleService(test_db_session, test_user)
    result = await svc.list_roles(
        limit=200,
        query_params_items=[("scope", "project")],
    )
    for r in result.resources:
        assert r.scope == "project", f"Role '{r.name}' has scope '{r.scope}'"
    names = _all_names(result)
    assert "project-admin" in names
    assert "project-user" in names
    assert "project-auditor" in names


# ============================================================================
# Role listing — pagination
# ============================================================================


@pytest.mark.asyncio
async def test_list_roles_pagination_no_duplicates(test_db_session: AsyncSession, test_user: User) -> None:
    """Paginating through all results produces no duplicates and no gaps."""
    svc = RoleService(test_db_session, test_user)
    db_names = await _create_db_roles(svc, 5)
    expected_total = ALL_BUILTIN_ROLE_COUNT + 5

    all_names: list[str] = []
    cursor = None
    page_count = 0
    while True:
        result = await svc.list_roles(limit=3, cursor=cursor)
        all_names.extend(r.name for r in result.resources)
        page_count += 1
        if not result.next:
            break
        cursor = result.next
        assert page_count < 20, "Too many pages — possible infinite loop"

    assert len(all_names) == expected_total, f"Expected {expected_total} items across all pages, got {len(all_names)}"
    assert len(set(all_names)) == len(all_names), (
        f"Duplicate names found: {[n for n in all_names if all_names.count(n) > 1]}"
    )
    for n in db_names:
        assert n in all_names


@pytest.mark.asyncio
async def test_list_roles_total_count_on_every_page(test_db_session: AsyncSession, test_user: User) -> None:
    """include_total should return the correct total on EVERY page, not just the first."""
    svc = RoleService(test_db_session, test_user)
    await _create_db_roles(svc, 5)
    expected_total = ALL_BUILTIN_ROLE_COUNT + 5

    cursor = None
    page_num = 0
    while True:
        result = await svc.list_roles(limit=3, cursor=cursor, include_total=True)
        page_num += 1
        assert result.total == expected_total, f"Page {page_num}: expected total={expected_total}, got {result.total}"
        if not result.next:
            break
        cursor = result.next
        assert page_num < 20, "Too many pages"


@pytest.mark.asyncio
async def test_list_roles_page_size_respected(test_db_session: AsyncSession, test_user: User) -> None:
    """Each page should contain at most `limit` items."""
    svc = RoleService(test_db_session, test_user)
    await _create_db_roles(svc, 10)
    limit = 4

    cursor = None
    while True:
        result = await svc.list_roles(limit=limit, cursor=cursor)
        assert len(result.resources) <= limit, f"Page has {len(result.resources)} items, limit is {limit}"
        if not result.next:
            break
        cursor = result.next


@pytest.mark.asyncio
async def test_list_roles_single_item_pages(test_db_session: AsyncSession, test_user: User) -> None:
    """Pagination works correctly with limit=1."""
    svc = RoleService(test_db_session, test_user)
    await _create_db_roles(svc, 2)
    expected_total = ALL_BUILTIN_ROLE_COUNT + 2

    all_names: list[str] = []
    cursor = None
    page_count = 0
    while True:
        result = await svc.list_roles(limit=1, cursor=cursor)
        assert len(result.resources) <= 1
        all_names.extend(r.name for r in result.resources)
        page_count += 1
        if not result.next:
            break
        cursor = result.next
        assert page_count < 50, "Too many pages"

    assert len(all_names) == expected_total
    assert len(set(all_names)) == len(all_names), "Duplicates found"


# ============================================================================
# Role listing — sorting
# ============================================================================


@pytest.mark.asyncio
async def test_list_roles_sort_by_name_asc_within_page(test_db_session: AsyncSession, test_user: User) -> None:
    """sort=name produces name-sorted results within each page.

    Global cross-page sort by name is not guaranteed for RoleService because
    it merges in-memory built-in roles with DB roles.  Each individual
    page should be sorted, and all items should still appear exactly once.
    """
    svc = RoleService(test_db_session, test_user)
    await _create_db_roles(svc, 5)
    expected_total = ALL_BUILTIN_ROLE_COUNT + 5

    all_names: list[str] = []
    cursor = None
    while True:
        result = await svc.list_roles(limit=4, cursor=cursor, sort="name")
        page_names = [r.name for r in result.resources]
        assert page_names == sorted(page_names), f"Page not sorted by name ASC: {page_names}"
        all_names.extend(page_names)
        if not result.next:
            break
        cursor = result.next

    assert len(all_names) == expected_total
    assert len(set(all_names)) == len(all_names), "Duplicates found"


@pytest.mark.asyncio
async def test_list_roles_sort_by_name_desc_within_page(test_db_session: AsyncSession, test_user: User) -> None:
    """sort=-name produces name-sorted (desc) results within each page."""
    svc = RoleService(test_db_session, test_user)
    await _create_db_roles(svc, 5)
    expected_total = ALL_BUILTIN_ROLE_COUNT + 5

    all_names: list[str] = []
    cursor = None
    while True:
        result = await svc.list_roles(limit=4, cursor=cursor, sort="-name")
        page_names = [r.name for r in result.resources]
        assert page_names == sorted(page_names, reverse=True), f"Page not sorted by name DESC: {page_names}"
        all_names.extend(page_names)
        if not result.next:
            break
        cursor = result.next

    assert len(all_names) == expected_total
    assert len(set(all_names)) == len(all_names), "Duplicates found"


@pytest.mark.asyncio
async def test_list_roles_sort_by_name_single_page(test_db_session: AsyncSession, test_user: User) -> None:
    """When all items fit on one page, sort=name is globally correct."""
    svc = RoleService(test_db_session, test_user)
    await _create_db_roles(svc, 3)
    result = await svc.list_roles(limit=200, sort="name")
    names = _all_names(result)
    assert names == sorted(names)


@pytest.mark.asyncio
async def test_list_roles_sort_by_is_builtin_asc(test_db_session: AsyncSession, test_user: User) -> None:
    """sort=is_builtin (ASC) should show DB items (false) before builtins (true)."""
    svc = RoleService(test_db_session, test_user)
    await _create_db_roles(svc, 3)

    all_resources: list[tuple[str, bool]] = []
    cursor = None
    while True:
        result = await svc.list_roles(limit=5, cursor=cursor, sort="is_builtin")
        all_resources.extend((r.name, r.is_builtin) for r in result.resources)
        if not result.next:
            break
        cursor = result.next

    builtin_flags = [b for _, b in all_resources]
    false_section = [b for b in builtin_flags if not b]
    true_section = [b for b in builtin_flags if b]
    assert builtin_flags == [*false_section, *true_section], (
        "is_builtin ASC: expected all False items before True items"
    )


# ============================================================================
# Policy listing — basic + filtering
# ============================================================================


@pytest.mark.asyncio
async def test_list_policies_includes_all_builtins(test_db_session: AsyncSession, test_user: User) -> None:
    """All builtin policies appear in the listing."""
    svc = PolicyService(test_db_session, test_user)
    result = await svc.list_policies(limit=200)
    names = _all_names(result)
    for p in BUILTIN_POLICIES:
        assert p.name in names, f"Builtin policy '{p.name}' missing"


@pytest.mark.asyncio
async def test_list_policies_total_count(test_db_session: AsyncSession, test_user: User) -> None:
    """include_total returns correct total including builtins and DB items."""
    svc = PolicyService(test_db_session, test_user)
    await _create_db_policies(svc, 3)
    result = await svc.list_policies(limit=200, include_total=True)
    assert result.total == ALL_BUILTIN_POLICY_COUNT + 3


@pytest.mark.asyncio
async def test_list_policies_filter_is_builtin_false(test_db_session: AsyncSession, test_user: User) -> None:
    """is_builtin=false returns only custom DB policies."""
    svc = PolicyService(test_db_session, test_user)
    await _create_db_policies(svc, 3)
    result = await svc.list_policies(
        limit=200,
        query_params_items=[("is_builtin", "false")],
    )
    assert len(result.resources) == 3
    for p in result.resources:
        assert p.is_builtin is False


@pytest.mark.asyncio
async def test_list_policies_filter_is_builtin_true(test_db_session: AsyncSession, test_user: User) -> None:
    """is_builtin=true returns only builtin policies."""
    svc = PolicyService(test_db_session, test_user)
    await _create_db_policies(svc, 3)
    result = await svc.list_policies(
        limit=200,
        query_params_items=[("is_builtin", "true")],
    )
    for p in result.resources:
        assert p.is_builtin is True, (
            f"Policy '{p.name}' has is_builtin={p.is_builtin} but appeared in is_builtin=true results"
        )
    assert len(result.resources) == ALL_BUILTIN_POLICY_COUNT


@pytest.mark.asyncio
async def test_list_policies_filter_scope(test_db_session: AsyncSession, test_user: User) -> None:
    """scope=project returns only project-scoped policies."""
    svc = PolicyService(test_db_session, test_user)
    result = await svc.list_policies(
        limit=200,
        query_params_items=[("scope", "project")],
    )
    for p in result.resources:
        assert p.scope == "project"
    assert len(result.resources) == len(PROJECT_BUILTIN_POLICIES)


@pytest.mark.asyncio
async def test_list_policies_filter_name_contains(test_db_session: AsyncSession, test_user: User) -> None:
    """name[contains] filter matches both builtins and DB policies."""
    svc = PolicyService(test_db_session, test_user)
    await _create_db_policies(svc, 2, prefix="workflow-custom")
    result = await svc.list_policies(
        limit=200,
        query_params_items=[("name[contains]", "workflow")],
    )
    for p in result.resources:
        assert "workflow" in p.name.lower()


# ============================================================================
# Policy listing — pagination
# ============================================================================


@pytest.mark.asyncio
async def test_list_policies_pagination_no_duplicates(test_db_session: AsyncSession, test_user: User) -> None:
    """Paginating through all policy results produces no duplicates or gaps."""
    svc = PolicyService(test_db_session, test_user)
    db_names = await _create_db_policies(svc, 5)
    expected_total = ALL_BUILTIN_POLICY_COUNT + 5

    all_names: list[str] = []
    cursor = None
    page_count = 0
    while True:
        result = await svc.list_policies(limit=10, cursor=cursor)
        all_names.extend(r.name for r in result.resources)
        page_count += 1
        if not result.next:
            break
        cursor = result.next
        assert page_count < 50, "Too many pages"

    assert len(all_names) == expected_total, f"Expected {expected_total} policies, got {len(all_names)}"
    assert len(set(all_names)) == len(all_names), "Duplicates found"
    for n in db_names:
        assert n in all_names


@pytest.mark.asyncio
async def test_list_policies_total_count_on_every_page(test_db_session: AsyncSession, test_user: User) -> None:
    """include_total should return the correct total on every page."""
    svc = PolicyService(test_db_session, test_user)
    await _create_db_policies(svc, 3)
    expected_total = ALL_BUILTIN_POLICY_COUNT + 3

    cursor = None
    page_num = 0
    while True:
        result = await svc.list_policies(limit=10, cursor=cursor, include_total=True)
        page_num += 1
        assert result.total == expected_total, f"Page {page_num}: expected total={expected_total}, got {result.total}"
        if not result.next:
            break
        cursor = result.next
        assert page_num < 50, "Too many pages"


@pytest.mark.asyncio
async def test_list_policies_sort_by_name_within_page(test_db_session: AsyncSession, test_user: User) -> None:
    """sort=name produces name-sorted results within each page."""
    svc = PolicyService(test_db_session, test_user)
    await _create_db_policies(svc, 3)
    expected_total = ALL_BUILTIN_POLICY_COUNT + 3

    all_names: list[str] = []
    cursor = None
    while True:
        result = await svc.list_policies(limit=10, cursor=cursor, sort="name")
        page_names = [r.name for r in result.resources]
        assert page_names == sorted(page_names), f"Page not sorted by name ASC: {page_names}"
        all_names.extend(page_names)
        if not result.next:
            break
        cursor = result.next

    assert len(all_names) == expected_total
    assert len(set(all_names)) == len(all_names), "Duplicates found"


@pytest.mark.asyncio
async def test_list_policies_sort_by_name_single_page(test_db_session: AsyncSession, test_user: User) -> None:
    """When all items fit on one page, sort=name is globally correct."""
    svc = PolicyService(test_db_session, test_user)
    await _create_db_policies(svc, 3)
    result = await svc.list_policies(limit=200, sort="name")
    names = _all_names(result)
    assert names == sorted(names)
