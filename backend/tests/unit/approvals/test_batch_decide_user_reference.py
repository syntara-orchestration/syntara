"""batch_decide must report the acting principal's real type, not assume a user.

Service-account tokens act through the same ``User``-shaped dependency
(``syntara.auth.dependencies``), so a hardcoded ``type=user`` on the batch
result would send clients to a user page that does not exist.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import uuid4

import pytest
from sqlalchemy import delete
from sqlmodel import col

from syntara.approvals.models import ApprovalRequest, BatchApprovalDecision, BatchApprovalRequest
from syntara.approvals.services.approval_service import ApprovalService
from syntara.core.models import User
from syntara.core.models.principal import Principal, PrincipalType
from syntara.service_accounts.models.service_account import ServiceAccount
from tests.unit.approvals.test_approval_concurrency import (  # noqa: F401 - fixtures re-exported for this module
    _concurrency_data,
    _mock_evaluator_for_concurrency_tests,
    mock_workflow_client,
)

if TYPE_CHECKING:
    from unittest.mock import AsyncMock

    from sqlalchemy.ext.asyncio import async_sessionmaker
    from sqlmodel.ext.asyncio.session import AsyncSession


@pytest.mark.asyncio
async def test_batch_decide_reports_service_account_actor_type(
    test_session_factory: async_sessionmaker[AsyncSession],
    mock_workflow_client: AsyncMock,  # noqa: F811
) -> None:
    sa_name = f"batch-sa-{uuid4().hex[:8]}"
    async with _concurrency_data(test_session_factory, user_count=1, approval_count=1) as (
        user_ids,
        approval_ids,
    ):
        async with test_session_factory() as session:
            approval = await session.get(ApprovalRequest, approval_ids[0])
            assert approval is not None
            sa = ServiceAccount(name=sa_name, project_id=approval.project_id, created_by=user_ids[0])
            session.add(sa)  # the principals row is created by the before_flush hook
            await session.commit()
            sa_id = sa.id

        try:
            # Mirror how a service-account token is presented to services.
            actor = User(id=sa_id, username=sa_name, email=f"{sa_name}@example.com", is_enabled=True)
            object.__setattr__(actor, "__principal_type__", PrincipalType.SERVICE_ACCOUNT)

            async with test_session_factory() as session:
                service = ApprovalService(session, actor)
                response = await service.batch_decide(
                    BatchApprovalRequest(
                        decisions=[BatchApprovalDecision(approval_id=approval_ids[0], status="approved", note="sa")]
                    )
                )

            assert response.total_success == 1, response
            decided_by = response.results[0].decided_by
            assert decided_by is not None
            assert decided_by.type == "service_account"
            assert decided_by.name == sa_name
        finally:
            # FK order: the decided approval references the SA principal, and the SA
            # references the project that _concurrency_data deletes on exit.
            async with test_session_factory() as session:
                await session.exec(delete(ApprovalRequest).where(col(ApprovalRequest.id).in_(approval_ids)))
                await session.exec(delete(ServiceAccount).where(col(ServiceAccount.id) == sa_id))
                await session.exec(delete(Principal).where(col(Principal.id) == sa_id))
                await session.commit()
