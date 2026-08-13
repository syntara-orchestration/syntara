"""Integration tests for bidirectional cursor-based pagination.

This test suite validates that cursor-based pagination works correctly
for forward (Next) and backward (Previous) navigation across the entire
dataset, including edge cases.
"""

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
import pytest_asyncio
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.core.models import User
from syntara.core.utils.cursor import decode_cursor
from syntara.workflows.models.workflow import Workflow
from syntara.workflows.services import WorkflowService
from tests.helpers.workflow import create_minimal_workflow_definition

DATASET_SIZE = 25  # Number of workflows created by workflows_dataset fixture


@pytest_asyncio.fixture
async def workflows_dataset(test_db_session: AsyncSession, test_user: User, test_project_id: UUID) -> list[Workflow]:
    """Create a dataset of workflows with predictable timestamps for testing pagination.

    Creates DATASET_SIZE workflows with timestamps spaced 1 hour apart, ensuring
    a deterministic ordering for pagination tests.

    Args:
        test_db_session: Database session
        test_user: Admin user for creating workflows
        test_project_id: Project ID for workflow creation

    Returns:
        List of created workflows in chronological order (oldest to newest)

    """
    service = WorkflowService(test_db_session, test_user)
    workflows = []

    # Create DATASET_SIZE workflows with timestamps 1 hour apart
    base_time = datetime(2025, 1, 1, 0, 0, 0, tzinfo=UTC)

    for i in range(DATASET_SIZE):
        workflow, _, _ = await service.create_workflow(
            name=f"Test Workflow {i:02d}",
            description=f"Workflow for pagination testing - number {i}",
            labels={"test": "pagination", "index": str(i)},
            workflow_definition=create_minimal_workflow_definition(
                name=f"test-workflow-{i:02d}",
                description=f"Workflow for pagination testing - number {i}",
            ),
            project_id=test_project_id,
        )

        workflows.append(workflow)

    # Now update created_at timestamps for all workflows
    for i, workflow in enumerate(workflows):
        workflow.created_at = base_time + timedelta(hours=i)
        test_db_session.add(workflow)

    # Refresh all workflows to ensure they're up to date
    for workflow in workflows:
        await test_db_session.refresh(workflow)

    # Return in chronological order (oldest first)
    return workflows


class TestBidirectionalPagination:
    """Test cursor-based pagination in both directions (forward and backward)."""

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("workflows_dataset")
    async def test_forward_pagination_full_traversal(self, test_db_session: AsyncSession, test_user: User) -> None:
        """Test forward pagination (Next) through entire dataset.

        Validates that:
        1. First page has no prev cursor
        2. Each page returns correct number of items
        3. Next cursor advances through the dataset
        4. Last page has no next cursor
        """
        service = WorkflowService(test_db_session, test_user)
        page_size = 5
        pages_collected = []
        cursor = None

        # Calculate safety limit to prevent infinite loops
        # For 25 items with page_size=5, we expect ~5 pages, allow up to 7
        pagination_safety_limit = (DATASET_SIZE // page_size) + 2

        # Traverse forward through all pages
        while True:
            response = await service.list_workflows_cursor(
                limit=page_size,
                cursor=cursor,
                sort="-created_at",  # DESC: newest first
                query_params_items=[],
            )

            # Validate first page
            if cursor is None:
                assert response.prev is None, "First page should have prev=None"

            # If no next cursor, we've reached the end
            if response.next is None:
                # Last page can be empty or have items
                pages_collected.append(response)
                break

            # Non-last pages should have resources
            assert len(response.resources) > 0, "Non-last page should not be empty"
            pages_collected.append(response)

            # Move to next page
            cursor = response.next

            # Safety check: prevent infinite loops
            assert len(pages_collected) <= pagination_safety_limit, (
                f"Infinite loop detected in forward pagination: "
                f"collected {len(pages_collected)} pages, "
                f"expected ~{DATASET_SIZE // page_size} pages for {DATASET_SIZE} items"
            )

        # Validate total items collected (some pages may be empty at the end)
        total_items = sum(len(page.resources) for page in pages_collected)
        assert total_items == DATASET_SIZE, f"Expected {DATASET_SIZE} items, got {total_items}"

        # Validate page count (may have one extra empty page if last page was full)
        expected_pages_min = (DATASET_SIZE + page_size - 1) // page_size  # Minimum pages needed
        expected_pages_max = expected_pages_min + 1  # May have one extra empty page
        assert expected_pages_min <= len(pages_collected) <= expected_pages_max, (
            f"Expected {expected_pages_min}-{expected_pages_max} pages, got {len(pages_collected)}"
        )

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("workflows_dataset")
    async def test_backward_pagination_full_traversal(self, test_db_session: AsyncSession, test_user: User) -> None:
        """Test backward pagination (Previous) from end to beginning.

        Validates that:
        1. Can navigate backward from any page
        2. Prev cursor returns to previous pages
        3. Resources on backward pages match forward pages
        4. Reaches beginning (prev=None) correctly
        """
        service = WorkflowService(test_db_session, test_user)
        page_size = 5

        # Calculate safety limit to prevent infinite loops
        pagination_safety_limit = (DATASET_SIZE // page_size) + 2

        # First, navigate forward to the end to collect all pages
        forward_pages = []
        cursor = None

        while True:
            response = await service.list_workflows_cursor(
                limit=page_size,
                cursor=cursor,
                sort="-created_at",
                query_params_items=[],
            )
            forward_pages.append(response)

            if response.next is None:
                break

            cursor = response.next

        # Now navigate backward from the last non-empty page
        # (last page might be empty if dataset size is exactly divisible by page size)
        backward_pages = []
        last_page_with_prev = None
        for page in reversed(forward_pages):
            if page.prev is not None:
                last_page_with_prev = page
                break

        if last_page_with_prev is None:
            # Only one page exists, no backward navigation possible
            assert len(forward_pages) == 1, "Should only have 1 page if no prev cursor exists"
            return

        cursor = last_page_with_prev.prev

        while cursor:
            response = await service.list_workflows_cursor(
                limit=page_size,
                cursor=cursor,
                sort="-created_at",
                query_params_items=[],
            )
            backward_pages.append(response)

            # If we've reached the beginning, break
            if response.prev is None:
                break

            cursor = response.prev

            # Safety check: prevent infinite loops
            assert len(backward_pages) <= pagination_safety_limit, (
                f"Infinite loop detected in backward pagination: "
                f"collected {len(backward_pages)} pages, "
                f"expected ~{DATASET_SIZE // page_size} pages for {DATASET_SIZE} items"
            )

        # Validate we navigated back through all non-empty pages except the one we started from
        non_empty_forward_pages = [p for p in forward_pages if len(p.resources) > 0]
        expected_backward_pages = len(non_empty_forward_pages) - 1  # -1 because we start from second-to-last
        assert len(backward_pages) == expected_backward_pages, (
            f"Expected {expected_backward_pages} backward pages, got {len(backward_pages)}"
        )

        # Validate that backward pages match forward pages in reverse
        # Compare only non-empty pages
        for i, back_page in enumerate(backward_pages):
            # Map backward index to forward non-empty page index
            forward_idx = len(non_empty_forward_pages) - 2 - i  # -2 because we skip the page we started from

            if forward_idx < 0:
                break

            forward_page = non_empty_forward_pages[forward_idx]

            # Compare resource IDs
            back_ids = [str(r.id) for r in back_page.resources]
            forward_ids = [str(r.id) for r in forward_page.resources]

            assert back_ids == forward_ids, f"Page {forward_idx}: Backward and forward IDs don't match"

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("workflows_dataset")
    async def test_bidirectional_navigation_consistency(self, test_db_session: AsyncSession, test_user: User) -> None:
        """Test that forward and backward navigation are consistent.

        Navigates forward 3 pages, then backward 3 pages, and verifies
        we end up at the first page again.
        """
        service = WorkflowService(test_db_session, test_user)
        page_size = 5

        # Navigate forward 3 pages
        cursor = None
        for _ in range(3):
            response = await service.list_workflows_cursor(
                limit=page_size,
                cursor=cursor,
                sort="-created_at",
                query_params_items=[],
            )
            cursor = response.next
            assert cursor is not None, "Should have next cursor for first 3 pages"

        # Now navigate backward 3 pages using prev cursor
        third_page_prev = response.prev
        assert third_page_prev is not None, "Third page should have prev cursor"

        cursor = third_page_prev
        for i in range(2):  # Go back 2 more pages (3 total)
            response = await service.list_workflows_cursor(
                limit=page_size,
                cursor=cursor,
                sort="-created_at",
                query_params_items=[],
            )
            cursor = response.prev

            if i == 1:  # After going back 3 pages total, should be at first page
                assert response.prev is None, "Should reach first page after going back 3 times"

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("workflows_dataset")
    async def test_cursor_direction_encoding(self, test_db_session: AsyncSession, test_user: User) -> None:
        """Test that cursors correctly encode pagination direction.

        Validates that:
        1. Next cursors have direction="next"
        2. Prev cursors have direction="prev"
        3. Direction affects query results correctly
        """
        service = WorkflowService(test_db_session, test_user)

        # Get first page
        page1 = await service.list_workflows_cursor(
            limit=5,
            cursor=None,
            sort="-created_at",
            query_params_items=[],
        )

        # Decode and verify next cursor
        if page1.next:
            next_cursor_data = decode_cursor(page1.next)
            assert next_cursor_data["direction"] == "next", "Next cursor should have direction='next'"

        # Get second page
        page2 = await service.list_workflows_cursor(
            limit=5,
            cursor=page1.next,
            sort="-created_at",
            query_params_items=[],
        )

        # Decode and verify prev cursor
        if page2.prev:
            prev_cursor_data = decode_cursor(page2.prev)
            assert prev_cursor_data["direction"] == "prev", "Prev cursor should have direction='prev'"

    @pytest.mark.asyncio
    async def test_single_page_dataset(
        self, test_db_session: AsyncSession, test_user: User, test_project_id: UUID
    ) -> None:
        """Test pagination with a dataset that fits on a single page.

        When all data fits on one page:
        - prev should be None
        - next should be None
        """
        service = WorkflowService(test_db_session, test_user)

        # Create just 3 workflows (less than page size)
        for i in range(3):
            await service.create_workflow(
                name=f"Single Page Workflow {i}",
                description="Test",
                labels={},
                workflow_definition=create_minimal_workflow_definition(
                    name=f"single-page-workflow-{i}",
                    description="Test",
                ),
                project_id=test_project_id,
            )

        response = await service.list_workflows_cursor(
            limit=10,  # Larger than dataset
            cursor=None,
            sort="-created_at",
            query_params_items=[],
        )

        assert response.prev is None, "Single page should have prev=None"
        assert response.next is None, "Single page should have next=None"
        assert len(response.resources) == 3, "Should return all 3 workflows"

    @pytest.mark.asyncio
    async def test_empty_dataset_pagination(self, test_db_session: AsyncSession, test_user: User) -> None:
        """Test pagination with an empty dataset.

        Empty results should have:
        - prev = None
        - next = None
        - resources = []
        """
        service = WorkflowService(test_db_session, test_user)

        # Query with a filter that matches nothing
        response = await service.list_workflows_cursor(
            limit=10,
            cursor=None,
            sort="-created_at",
            query_params_items=[("name", "NonExistentWorkflow")],
        )

        assert response.prev is None, "Empty page should have prev=None"
        assert response.next is None, "Empty page should have next=None"
        assert len(response.resources) == 0, "Should return empty list"

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("workflows_dataset")
    async def test_pagination_with_asc_sort(self, test_db_session: AsyncSession, test_user: User) -> None:
        """Test bidirectional pagination with ASC sort order.

        Validates that pagination works correctly when sorted in ascending order
        (oldest first instead of newest first).
        """
        service = WorkflowService(test_db_session, test_user)
        page_size = 5

        # Get first page with ASC sort (oldest first)
        page1 = await service.list_workflows_cursor(
            limit=page_size,
            cursor=None,
            sort="created_at",  # ASC (no minus sign)
            query_params_items=[],
        )

        # Get second page
        page2 = await service.list_workflows_cursor(
            limit=page_size,
            cursor=page1.next,
            sort="created_at",
            query_params_items=[],
        )

        # Go back to first page using prev cursor
        page1_again = await service.list_workflows_cursor(
            limit=page_size,
            cursor=page2.prev,
            sort="created_at",
            query_params_items=[],
        )

        # Validate we got back to the first page
        page1_ids = [str(r.id) for r in page1.resources]
        page1_again_ids = [str(r.id) for r in page1_again.resources]

        assert page1_ids == page1_again_ids, "Going back should return to first page with ASC sort"
        assert page1_again.prev is None, "First page should have prev=None even with ASC sort"

    @pytest.mark.asyncio
    async def test_page_boundary_timestamps(
        self, test_db_session: AsyncSession, test_user: User, workflows_dataset: list[Workflow]
    ) -> None:
        """Test pagination handles items with identical timestamps correctly.

        When multiple items have the same timestamp, pagination should:
        1. Use the ID as a tiebreaker for stable ordering
        2. Not skip or duplicate items across page boundaries
        """
        service = WorkflowService(test_db_session, test_user)

        # Update 5 workflows to have identical timestamps
        same_timestamp = datetime(2025, 6, 15, 12, 0, 0, tzinfo=UTC)
        for i in range(5):
            workflows_dataset[i].created_at = same_timestamp
            test_db_session.add(workflows_dataset[i])
        await test_db_session.commit()

        # Get pages with size 3 (will split the same-timestamp items across pages)
        page1 = await service.list_workflows_cursor(
            limit=3,
            cursor=None,
            sort="-created_at",
            query_params_items=[],
        )

        page2 = await service.list_workflows_cursor(
            limit=3,
            cursor=page1.next,
            sort="-created_at",
            query_params_items=[],
        )

        # Collect all IDs from both pages
        all_ids = [str(r.id) for r in page1.resources] + [str(r.id) for r in page2.resources]

        # Verify no duplicates
        assert len(all_ids) == len(set(all_ids)), "Should not have duplicate items across pages"

        # Verify we can go back to page 1
        page1_again = await service.list_workflows_cursor(
            limit=3,
            cursor=page2.prev,
            sort="-created_at",
            query_params_items=[],
        )

        page1_ids = [str(r.id) for r in page1.resources]
        page1_again_ids = [str(r.id) for r in page1_again.resources]

        assert page1_ids == page1_again_ids, "Going back should return same items even with identical timestamps"

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("workflows_dataset")
    async def test_first_page_prev_cursor_is_null(self, test_db_session: AsyncSession, test_user: User) -> None:
        """Test that navigating backward to the first page sets prev=None.

        This test validates the fix for first page detection during backward navigation.
        When navigating backward to reach the first page, the prev cursor must be None.
        """
        service = WorkflowService(test_db_session, test_user)
        page_size = 5

        # Get first page (forward)
        page1_forward = await service.list_workflows_cursor(
            limit=page_size,
            cursor=None,
            sort="-created_at",
            query_params_items=[],
        )

        # First page should have prev=None
        assert page1_forward.prev is None, "First page (forward) should have prev=None"

        # Get second page
        page2 = await service.list_workflows_cursor(
            limit=page_size,
            cursor=page1_forward.next,
            sort="-created_at",
            query_params_items=[],
        )

        # Second page should have prev cursor
        assert page2.prev is not None, "Second page should have prev cursor"

        # Navigate backward to first page
        page1_backward = await service.list_workflows_cursor(
            limit=page_size,
            cursor=page2.prev,
            sort="-created_at",
            query_params_items=[],
        )

        # First page (reached via backward navigation) should have prev=None
        assert page1_backward.prev is None, "First page (backward) must have prev=None"

        # Verify the content matches
        page1_forward_ids = [str(r.id) for r in page1_forward.resources]
        page1_backward_ids = [str(r.id) for r in page1_backward.resources]
        assert page1_forward_ids == page1_backward_ids, "First page content should match forward and backward"

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("workflows_dataset")
    async def test_backward_navigation_maintains_sort_order(
        self, test_db_session: AsyncSession, test_user: User
    ) -> None:
        """Test that backward navigation maintains the same sort order as forward navigation.

        This test validates the fix for backward pagination result ordering.
        Items should appear in the same order whether navigating forward or backward.
        """
        service = WorkflowService(test_db_session, test_user)
        page_size = 5

        # Navigate forward to collect pages
        forward_pages = []
        cursor = None
        for _ in range(3):  # Get first 3 pages
            page = await service.list_workflows_cursor(
                limit=page_size,
                cursor=cursor,
                sort="-created_at",
                query_params_items=[],
            )
            forward_pages.append(page)
            cursor = page.next
            if cursor is None:
                break

        # Navigate backward from page 3 to page 2
        if len(forward_pages) >= 3:
            page2_backward = await service.list_workflows_cursor(
                limit=page_size,
                cursor=forward_pages[2].prev,
                sort="-created_at",
                query_params_items=[],
            )

            # Verify resources are in the same order
            page2_forward_ids = [str(r.id) for r in forward_pages[1].resources]
            page2_backward_ids = [str(r.id) for r in page2_backward.resources]

            assert page2_forward_ids == page2_backward_ids, "Page 2: IDs should be in same order forward and backward"

            # Verify individual item order is preserved
            for i, (fwd_id, bwd_id) in enumerate(zip(page2_forward_ids, page2_backward_ids, strict=True)):
                assert fwd_id == bwd_id, f"Item {i}: Forward ID {fwd_id} != Backward ID {bwd_id}"

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("workflows_dataset")
    async def test_backward_pagination_with_desc_sort_ordering(
        self, test_db_session: AsyncSession, test_user: User
    ) -> None:
        """Test that DESC sort order is preserved during backward pagination.

        When navigating backward with DESC sort, items should still be returned
        in descending order (newest to oldest), not reversed.
        """
        service = WorkflowService(test_db_session, test_user)
        page_size = 5

        # Get page 1 (should have newest items)
        page1 = await service.list_workflows_cursor(
            limit=page_size,
            cursor=None,
            sort="-created_at",  # DESC
            query_params_items=[],
        )

        # Get page 2
        page2 = await service.list_workflows_cursor(
            limit=page_size,
            cursor=page1.next,
            sort="-created_at",
            query_params_items=[],
        )

        # Navigate backward to page 1
        page1_backward = await service.list_workflows_cursor(
            limit=page_size,
            cursor=page2.prev,
            sort="-created_at",
            query_params_items=[],
        )

        # Verify timestamps are in descending order (newest first)
        for i in range(len(page1_backward.resources) - 1):
            current_time = page1_backward.resources[i].created_at
            next_time = page1_backward.resources[i + 1].created_at
            assert current_time >= next_time, f"DESC sort: Item {i} timestamp should be >= item {i + 1}"

        # Verify the order matches forward navigation
        page1_ids = [str(r.id) for r in page1.resources]
        page1_backward_ids = [str(r.id) for r in page1_backward.resources]
        assert page1_ids == page1_backward_ids, "Page 1: Order should match between forward and backward"

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("workflows_dataset")
    async def test_backward_pagination_page_boundaries(self, test_db_session: AsyncSession, test_user: User) -> None:
        """Test that page boundaries are correct during backward navigation.

        Validates that:
        - First page has prev=None
        - Middle pages have both prev and next
        - Last page has next=None
        - Navigating backward from last page returns correct pages
        """
        service = WorkflowService(test_db_session, test_user)
        page_size = 5

        # Navigate to last page
        forward_pages = []
        cursor = None
        while True:
            page = await service.list_workflows_cursor(
                limit=page_size,
                cursor=cursor,
                sort="-created_at",
                query_params_items=[],
            )
            forward_pages.append(page)
            if page.next is None:
                break
            cursor = page.next

        # Verify first page boundaries
        assert forward_pages[0].prev is None, "First page should have prev=None"
        assert forward_pages[0].next is not None, "First page should have next cursor"

        # Verify last page boundaries
        assert forward_pages[-1].next is None, "Last page should have next=None"
        # Last page should have prev cursor only if it has items
        if len(forward_pages[-1].resources) > 0:
            assert forward_pages[-1].prev is not None, "Last page with items should have prev cursor"

        # Navigate backward from last page (if it has prev cursor)
        backward_pages = []
        cursor = forward_pages[-1].prev
        if cursor:  # Only navigate backward if there's a prev cursor
            while cursor:
                page = await service.list_workflows_cursor(
                    limit=page_size,
                    cursor=cursor,
                    sort="-created_at",
                    query_params_items=[],
                )
                backward_pages.append(page)
                if page.prev is None:
                    # Reached first page
                    assert len(backward_pages) == len(forward_pages) - 1, "Should traverse N-1 pages backward"
                    break
                cursor = page.prev

            # Verify we reached the first page with prev=None
            assert backward_pages[-1].prev is None, "Last backward page (first page) should have prev=None"

    @pytest.mark.asyncio
    async def test_backward_pagination_single_item_pages(
        self, test_db_session: AsyncSession, test_user: User, test_project_id: UUID
    ) -> None:
        """Test backward pagination with single-item pages.

        Edge case: When page size is 1, backward navigation should still work correctly.
        """
        service = WorkflowService(test_db_session, test_user)

        # Create 3 workflows
        for i in range(3):
            await service.create_workflow(
                name=f"Single Item Test {i}",
                description="Test",
                labels={},
                workflow_definition=create_minimal_workflow_definition(
                    name=f"single-item-test-{i}",
                    description="Test",
                ),
                project_id=test_project_id,
            )

        # Get page 1 (1 item)
        page1 = await service.list_workflows_cursor(
            limit=1,
            cursor=None,
            sort="-created_at",
            query_params_items=[],
        )

        assert len(page1.resources) == 1, "Page 1 should have 1 item"
        assert page1.prev is None, "Page 1 should have prev=None"
        assert page1.next is not None, "Page 1 should have next cursor"

        # Get page 2 (1 item)
        page2 = await service.list_workflows_cursor(
            limit=1,
            cursor=page1.next,
            sort="-created_at",
            query_params_items=[],
        )

        assert len(page2.resources) == 1, "Page 2 should have 1 item"
        assert page2.prev is not None, "Page 2 should have prev cursor"

        # Navigate backward to page 1
        page1_backward = await service.list_workflows_cursor(
            limit=1,
            cursor=page2.prev,
            sort="-created_at",
            query_params_items=[],
        )

        assert len(page1_backward.resources) == 1, "Page 1 backward should have 1 item"
        assert page1_backward.prev is None, "Page 1 backward should have prev=None"
        assert str(page1.resources[0].id) == str(page1_backward.resources[0].id), "Should return same item"


@pytest.mark.asyncio
class TestBidirectionalPaginationSortByName:
    """Verify cursor pagination works correctly when sorting by name (non-default)."""

    async def test_forward_pagination_sort_name_asc_global_order(
        self, test_db_session: AsyncSession, test_user: User, workflows_dataset: list[Workflow]
    ) -> None:
        """All items collected via forward pagination should be globally sorted by name ASC."""
        service = WorkflowService(test_db_session, test_user)

        all_names: list[str] = []
        cursor = None
        while True:
            page = await service.list_workflows_cursor(
                limit=5,
                cursor=cursor,
                sort="name",
                query_params_items=[],
            )
            all_names.extend(r.name for r in page.resources)
            if not page.next:
                break
            cursor = page.next

        assert len(all_names) == DATASET_SIZE
        assert all_names == sorted(all_names), f"Global name ASC order broken: {all_names}"
        assert len(set(all_names)) == len(all_names), "Duplicates found"

    async def test_forward_pagination_sort_name_desc_global_order(
        self, test_db_session: AsyncSession, test_user: User, workflows_dataset: list[Workflow]
    ) -> None:
        """All items collected via forward pagination should be globally sorted by name DESC."""
        service = WorkflowService(test_db_session, test_user)

        all_names: list[str] = []
        cursor = None
        while True:
            page = await service.list_workflows_cursor(
                limit=5,
                cursor=cursor,
                sort="-name",
                query_params_items=[],
            )
            all_names.extend(r.name for r in page.resources)
            if not page.next:
                break
            cursor = page.next

        assert len(all_names) == DATASET_SIZE
        assert all_names == sorted(all_names, reverse=True), f"Global name DESC order broken: {all_names}"
        assert len(set(all_names)) == len(all_names), "Duplicates found"

    async def test_bidirectional_sort_name_roundtrip(
        self, test_db_session: AsyncSession, test_user: User, workflows_dataset: list[Workflow]
    ) -> None:
        """Navigating forward then backward by name returns consistent results."""
        service = WorkflowService(test_db_session, test_user)

        page1 = await service.list_workflows_cursor(
            limit=5,
            cursor=None,
            sort="name",
            query_params_items=[],
        )
        assert len(page1.resources) == 5
        assert page1.next is not None

        page2 = await service.list_workflows_cursor(
            limit=5,
            cursor=page1.next,
            sort="name",
            query_params_items=[],
        )
        assert len(page2.resources) == 5
        assert page2.prev is not None

        page1_back = await service.list_workflows_cursor(
            limit=5,
            cursor=page2.prev,
            sort="name",
            query_params_items=[],
        )
        page1_ids = [str(r.id) for r in page1.resources]
        page1_back_ids = [str(r.id) for r in page1_back.resources]
        assert page1_ids == page1_back_ids, "Backward navigation should return same items"
