"""Integration tests for Execution Plane callback service authorization."""

from collections.abc import Callable
from contextlib import AbstractContextManager

import pytest
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.authz.models.assignments import RoleAssignment
from syntara.authz.seed import seed_authz_data
from syntara.core.config.base import get_settings
from syntara.core.models.principal import Principal, service_principal_id

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_execution_plane_callback_principal_is_seeded(
    test_db_session: AsyncSession,
    override_settings: Callable[..., AbstractContextManager[object]],
) -> None:
    """The configured EP certificate identity receives only its callback role."""
    with override_settings(ep_callback_service_cn="execution-plane.k8s.serviceaccount"):
        certificate_cn = get_settings().ep_callback_service_cn
        await seed_authz_data(test_db_session)

    principal_id = service_principal_id(certificate_cn)

    principal = await test_db_session.get(Principal, principal_id)
    assert principal is not None
    assert principal.principal_type == "service"

    assignments = await test_db_session.exec(
        select(RoleAssignment).where(
            RoleAssignment.principal_id == principal_id,
            RoleAssignment.project_id.is_(None),  # type: ignore[union-attr]
        )
    )
    assert [assignment.role_name for assignment in assignments.all()] == ["execution-plane-callback"]
