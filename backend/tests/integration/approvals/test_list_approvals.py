"""Contract tests for GET /api/v1/approvals endpoint.

Tests validation of OpenAPI schema compliance including:
- Response shape matches OpenAPI specification
- Pagination fields are present and correctly typed
- Status enum values are valid
- Filter parameters work as expected

Task T026 from AAP-64408 acceptance criteria.
"""

import pytest
from httpx import AsyncClient

from syntara.approvals.models import ApprovalRequestStatus
from tests.integration.helpers.approval import ApprovalsFactory
from tests.integration.helpers.error_data import assert_error_data
from tests.integration.helpers.workflow import ExecutionsFactory


class TestListApprovalsContract:
    """Contract tests for GET /api/v1/approvals endpoint."""

    @pytest.mark.asyncio
    async def test_list_approvals_empty_response_schema(
        self,
        auth_client: AsyncClient,
    ) -> None:
        """Test that empty list response matches OpenAPI schema.

        Validates:
        - Response structure for empty results
        - Required pagination metadata fields
        - Proper HTTP status code
        """
        # Act
        response = await auth_client.get("/api/v1/approvals")

        # Assert
        assert response.status_code == 200
        data = response.json()

        # Validate required pagination fields per OpenAPI spec
        assert "resources" in data
        assert "next" in data
        assert "prev" in data
        assert isinstance(data["resources"], list)
        assert len(data["resources"]) == 0
        assert data["next"] is None
        assert data["prev"] is None

    @pytest.mark.asyncio
    async def test_list_approvals_with_data_response_schema(
        self,
        auth_client: AsyncClient,
        approvals_factory: ApprovalsFactory,
        executions_factory: ExecutionsFactory,
    ) -> None:
        """Test that populated list response matches OpenAPI schema.

        Validates:
        - Response structure with approval data
        - Approval object fields match OpenAPI spec
        - Status enum values are correct
        - Nullable fields handled properly
        """
        # Arrange - Create executions first, then test approvals with mixed statuses
        executions = await executions_factory.create_executions(count=4)
        await approvals_factory.create_mixed_status_approvals(
            pending_count=2, approved_count=1, rejected_count=1, execution_id=executions[0].id
        )

        # Act
        response = await auth_client.get("/api/v1/approvals")

        # Assert
        assert response.status_code == 200
        data = response.json()

        # Validate pagination structure
        assert "resources" in data
        assert "next" in data
        assert "prev" in data
        assert isinstance(data["resources"], list)
        assert len(data["resources"]) == 4  # 2 pending + 1 approved + 1 rejected

        # Validate first approval object matches OpenAPI schema
        approval = data["resources"][0]
        required_fields = [
            "id",
            "execution_id",
            "approval_node_id",
            "name",
            "status",
            "next_step_approved",
            "workflow_context",
            "created_at",
            "updated_at",
        ]
        for field in required_fields:
            assert field in approval, f"Required field '{field}' missing from approval response"

        # Validate status enum values
        valid_statuses = {status.value for status in ApprovalRequestStatus}
        for approval_item in data["resources"]:
            assert approval_item["status"] in valid_statuses

        # Validate nullable fields (should be present but may be null)
        nullable_fields = [
            "timeout_at",
            "next_step_rejected",
            "decided_by",
            "decided_at",
            "decision_notes",
            "prompt",
        ]
        for field in nullable_fields:
            assert field in approval, f"Nullable field '{field}' missing from approval response"

    @pytest.mark.asyncio
    async def test_list_approvals_pagination_parameters(
        self,
        auth_client: AsyncClient,
        approvals_factory: ApprovalsFactory,
        executions_factory: ExecutionsFactory,
    ) -> None:
        """Test pagination parameters work correctly.

        Validates:
        - limit parameter controls response size
        - cursor parameter enables pagination
        - sort parameter affects ordering
        - include_total parameter adds total count
        """
        # Arrange - Create executions first, then enough approvals for pagination
        executions = await executions_factory.create_executions(count=15)
        await approvals_factory.create_pending_approvals(count=15, execution_id=executions[0].id)

        # Act & Assert - Test limit parameter
        response = await auth_client.get("/api/v1/approvals?limit=5")
        assert response.status_code == 200
        data = response.json()
        assert len(data["resources"]) == 5
        assert data["next"] is not None  # Should have next cursor

        # Act & Assert - Test include_total parameter
        response = await auth_client.get("/api/v1/approvals?include_total=true")
        assert response.status_code == 200
        data = response.json()
        assert "total" in data
        assert data["total"] == 15

    @pytest.mark.asyncio
    async def test_list_approvals_pagination_cursor_navigation(
        self,
        auth_client: AsyncClient,
        approvals_factory: ApprovalsFactory,
        executions_factory: ExecutionsFactory,
    ) -> None:
        """Test that cursor-based pagination navigation works correctly.

        Validates:
        - First page returns items and next cursor
        - Next cursor retrieves subsequent items
        - No duplicate items between pages
        - Final page has has_next=false and next_cursor=null
        """
        # Arrange - Create executions first, then 7 approvals to test multi-page navigation
        executions = await executions_factory.create_executions(count=7)
        await approvals_factory.create_pending_approvals(count=7, execution_id=executions[0].id)

        # Act & Assert - Get first page
        response = await auth_client.get("/api/v1/approvals?limit=3")
        assert response.status_code == 200
        first_page = response.json()

        assert len(first_page["resources"]) == 3
        assert first_page["next"] is not None  # Should have next cursor
        assert first_page["prev"] is None  # First page has no prev
        first_page_ids = {item["id"] for item in first_page["resources"]}

        # Act & Assert - Get second page using cursor
        next_cursor = first_page["next"]
        response = await auth_client.get(f"/api/v1/approvals?limit=3&cursor={next_cursor}")
        assert response.status_code == 200
        second_page = response.json()

        assert len(second_page["resources"]) == 3
        assert second_page["next"] is not None  # Should have next cursor
        assert second_page["prev"] is not None  # Should have prev cursor now
        second_page_ids = {item["id"] for item in second_page["resources"]}

        # Ensure no duplicate items between pages
        assert first_page_ids.isdisjoint(second_page_ids)

        # Act & Assert - Get third page (final page)
        next_cursor = second_page["next"]
        response = await auth_client.get(f"/api/v1/approvals?limit=3&cursor={next_cursor}")
        assert response.status_code == 200
        third_page = response.json()

        assert len(third_page["resources"]) == 1  # Only 1 item remaining
        assert third_page["next"] is None  # Final page has no next
        assert third_page["prev"] is not None  # Should have prev cursor

    @pytest.mark.asyncio
    async def test_list_approvals_sorting_functionality(
        self,
        auth_client: AsyncClient,
        approvals_factory: ApprovalsFactory,
        executions_factory: ExecutionsFactory,
    ) -> None:
        """Test that sorting parameters work correctly.

        Validates:
        - Sort by name ascending and descending
        - Sort by created_at ascending and descending
        - Sorted results are in expected order
        """
        # Arrange - Create executions first, then approvals with predictable names for sorting
        alpha_executions = await executions_factory.create_executions(count=3)
        beta_executions = await executions_factory.create_executions(count=2)
        await approvals_factory.create_approvals(
            count=3,
            name_prefix="Alpha Approval",
            statuses=[ApprovalRequestStatus.PENDING],
            execution_id=alpha_executions[0].id,
        )
        await approvals_factory.create_approvals(
            count=2,
            name_prefix="Beta Approval",
            statuses=[ApprovalRequestStatus.APPROVED],
            execution_id=beta_executions[0].id,
        )

        # Act & Assert - Test sort by name ascending (Alpha before Beta)
        response = await auth_client.get("/api/v1/approvals?sort=name")
        assert response.status_code == 200
        data = response.json()

        names = [item["name"] for item in data["resources"]]
        assert len(names) == 5
        # Should be in ascending order (Alpha before Beta)
        assert names == sorted(names)

        # Act & Assert - Test sort by name descending (Beta before Alpha)
        response = await auth_client.get("/api/v1/approvals?sort=-name")
        assert response.status_code == 200
        data = response.json()

        names = [item["name"] for item in data["resources"]]
        assert len(names) == 5
        # Should be in descending order (Beta before Alpha)
        assert names == sorted(names, reverse=True)

        # Act & Assert - Test sort by created_at ascending (default timestamp sorting)
        response = await auth_client.get("/api/v1/approvals?sort=created_at")
        assert response.status_code == 200
        data = response.json()

        created_ats = [item["created_at"] for item in data["resources"]]
        assert len(created_ats) == 5
        # Should be in ascending order
        assert created_ats == sorted(created_ats)

        # Act & Assert - Test sort by created_at descending
        response = await auth_client.get("/api/v1/approvals?sort=-created_at")
        assert response.status_code == 200
        data = response.json()

        created_ats = [item["created_at"] for item in data["resources"]]
        assert len(created_ats) == 5
        # Should be in descending order
        assert created_ats == sorted(created_ats, reverse=True)

    @pytest.mark.asyncio
    async def test_list_approvals_filter_parameters(
        self,
        auth_client: AsyncClient,
        approvals_factory: ApprovalsFactory,
        executions_factory: ExecutionsFactory,
    ) -> None:
        """Test filter parameters work correctly.

        Validates:
        - status filter returns only matching approvals
        - execution_id filter returns only matching approvals
        """
        # Arrange - Create executions first, then approvals with different statuses
        pending_executions = await executions_factory.create_executions(count=3)
        approved_executions = await executions_factory.create_executions(count=2)
        pending_approvals = await approvals_factory.create_pending_approvals(
            count=3, execution_id=pending_executions[0].id
        )
        await approvals_factory.create_approvals(
            count=2, statuses=[ApprovalRequestStatus.APPROVED], execution_id=approved_executions[0].id
        )

        # Act & Assert - Test status filter for pending
        response = await auth_client.get("/api/v1/approvals?status=pending")
        assert response.status_code == 200
        data = response.json()
        assert len(data["resources"]) == 3
        for approval in data["resources"]:
            assert approval["status"] == "pending"

        # Act & Assert - Test status filter for approved
        response = await auth_client.get("/api/v1/approvals?status=approved")
        assert response.status_code == 200
        data = response.json()
        assert len(data["resources"]) == 2
        for approval in data["resources"]:
            assert approval["status"] == "approved"

        # Act & Assert - Test execution_id filter
        execution_id = str(pending_approvals[0].execution_id)
        response = await auth_client.get(f"/api/v1/approvals?execution_id={execution_id}")
        assert response.status_code == 200
        data = response.json()
        for approval in data["resources"]:
            assert approval["execution_id"] == execution_id

    @pytest.mark.asyncio
    async def test_list_approvals_in_operator_filters_by_status(
        self,
        auth_client: AsyncClient,
        approvals_factory: ApprovalsFactory,
        executions_factory: ExecutionsFactory,
    ) -> None:
        """Test that status[in]=pending,expired returns only matching approvals.

        Covers the primary UI use case for multi-value OR filtering on a
        story endpoint (approvals) rather than just tools.
        """
        executions = await executions_factory.create_executions(count=5)
        await approvals_factory.create_approvals(
            count=5,
            statuses=[
                ApprovalRequestStatus.PENDING,
                ApprovalRequestStatus.APPROVED,
                ApprovalRequestStatus.REJECTED,
                ApprovalRequestStatus.EXPIRED,
                ApprovalRequestStatus.CANCELLED,
            ],
            execution_id=executions[0].id,
        )

        response = await auth_client.get(
            "/api/v1/approvals",
            params={"status[in]": "pending,expired"},
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["resources"]) == 2
        returned_statuses = {a["status"] for a in data["resources"]}
        assert returned_statuses == {"pending", "expired"}

    @pytest.mark.asyncio
    async def test_list_approvals_invalid_parameters_error_response(
        self,
        auth_client: AsyncClient,
    ) -> None:
        """Test that invalid query parameters return proper error responses.

        Validates:
        - Invalid status values return 422 Unprocessable Entity
        - Invalid UUIDs return 422 Unprocessable Entity
        - Invalid limit values return 422 Unprocessable Entity
        - Error responses match RFC 9457 format
        """
        # Act & Assert - Invalid status value
        response = await auth_client.get("/api/v1/approvals?status=invalid")
        assert response.status_code == 422
        assert_error_data(
            response,
            error_type="https://api.example.com/errors/validation-error",
            title="Request Validation Error",
            detail=(
                "Validation failed: query -> status: "
                "Input should be 'pending', 'approved', 'rejected', 'expired' or 'cancelled'"
            ),
            code="REQUEST_VALIDATION_ERROR",
            retryable=False,
        )

        # Act & Assert - Invalid execution_id format
        response = await auth_client.get("/api/v1/approvals?execution_id=not-a-uuid")
        assert response.status_code == 422
        assert_error_data(
            response,
            error_type="https://api.example.com/errors/validation-error",
            title="Request Validation Error",
            detail=(
                "Validation failed: query -> execution_id: Input should be a valid UUID, "
                "invalid character: found `n` at 1"
            ),
            code="REQUEST_VALIDATION_ERROR",
            retryable=False,
        )

        # Act & Assert - Invalid limit value
        response = await auth_client.get("/api/v1/approvals?limit=0")
        assert response.status_code == 422
        assert_error_data(
            response,
            error_type="https://api.example.com/errors/validation-error",
            title="Request Validation Error",
            detail="Validation failed: query -> limit: Input should be greater than 0",
            code="REQUEST_VALIDATION_ERROR",
            retryable=False,
        )

        response = await auth_client.get("/api/v1/approvals?limit=101")  # Over max
        assert response.status_code == 422
        assert_error_data(
            response,
            error_type="https://api.example.com/errors/validation-error",
            title="Request Validation Error",
            detail="Validation failed: query -> limit: Input should be less than or equal to 100",
            code="REQUEST_VALIDATION_ERROR",
            retryable=False,
        )
