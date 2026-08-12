"""DB-level model tests for Integration and related cascade behavior."""

from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.core.models import User
from syntara.integrations.models.integration import Integration, IntegrationType
from syntara.integrations.models.integration_configuration import MCPServerConfiguration
from syntara.tool_manager.models.tool import Tool, ToolParameter, ToolParameterType
from tests.integration.helpers.integration import IntegrationFactory


class TestIntegrationToolsRelationship:
    """Tests for querying tools by integration_id and tool parameter loading."""

    async def test_tools_query_by_integration_id(
        self,
        test_db_session: AsyncSession,
        test_user: User,
        integration_factory: IntegrationFactory,
    ) -> None:
        """Tools can be queried by integration_id using selectinload on parameters."""
        integration = await integration_factory.create()
        tool1 = Tool(
            integration_id=integration.id,
            name="Tool Alpha",
            namespaced_name=f"ns::alpha_{uuid4().hex[:6]}",
            created_by=test_user.id,
        )
        tool2 = Tool(
            integration_id=integration.id,
            name="Tool Beta",
            namespaced_name=f"ns::beta_{uuid4().hex[:6]}",
            created_by=test_user.id,
        )
        test_db_session.add_all([tool1, tool2])
        await test_db_session.commit()

        result = await test_db_session.exec(
            select(Tool)
            .options(selectinload(Tool.parameters))  # type: ignore[arg-type]
            .where(Tool.integration_id == integration.id)
        )
        tools = result.all()
        assert len(tools) == 2
        names = {t.name for t in tools}
        assert names == {"Tool Alpha", "Tool Beta"}

    async def test_tool_parameters_loaded_via_selectinload(
        self,
        test_db_session: AsyncSession,
        test_user: User,
        integration_factory: IntegrationFactory,
    ) -> None:
        """Tool parameters are loadable via selectinload without extra queries."""
        integration = await integration_factory.create()
        tool = Tool(
            integration_id=integration.id,
            name="Parameterized Tool",
            namespaced_name=f"ns::param_{uuid4().hex[:6]}",
            created_by=test_user.id,
        )
        test_db_session.add(tool)
        await test_db_session.flush()

        param = ToolParameter(
            tool_id=tool.id,
            name="my_param",
            type=ToolParameterType.STRING,
            description="A test param",
            required=True,
            created_by=test_user.id,
        )
        test_db_session.add(param)
        await test_db_session.commit()

        result = await test_db_session.exec(
            select(Tool)
            .options(selectinload(Tool.parameters))  # type: ignore[arg-type]
            .where(Tool.id == tool.id)
        )
        loaded = result.one()
        assert len(loaded.parameters) == 1
        assert loaded.parameters[0].name == "my_param"

    async def test_no_tools_for_new_integration(
        self,
        test_db_session: AsyncSession,
        integration_factory: IntegrationFactory,
    ) -> None:
        """A newly created integration has no associated tools."""
        integration = await integration_factory.create()
        await test_db_session.commit()

        result = await test_db_session.exec(select(Tool).where(Tool.integration_id == integration.id))
        assert result.all() == []


class TestIntegrationDeleteCascadesToTools:
    """Tests for CASCADE behavior on Tool.integration_id when Integration is deleted."""

    async def test_delete_integration_deletes_tools(
        self,
        test_db_session: AsyncSession,
        test_user: User,
        integration_factory: IntegrationFactory,
    ) -> None:
        """Deleting an Integration cascade-deletes its tools."""
        integration = await integration_factory.create()
        tool = Tool(
            integration_id=integration.id,
            name="Cascade Tool",
            namespaced_name=f"ns::cascade_{uuid4().hex[:6]}",
            created_by=test_user.id,
        )
        test_db_session.add(tool)
        await test_db_session.commit()

        tool_id = tool.id
        await test_db_session.delete(integration)
        await test_db_session.commit()
        test_db_session.expire_all()

        remaining = (await test_db_session.exec(select(Tool).where(Tool.id == tool_id))).one_or_none()
        assert remaining is None

    async def test_delete_integration_only_deletes_its_own_tools(
        self,
        test_db_session: AsyncSession,
        test_user: User,
        integration_factory: IntegrationFactory,
    ) -> None:
        """Deleting one integration does not affect tools on a different integration."""
        int_a = await integration_factory.create()
        int_b = await integration_factory.create()

        tool_a = Tool(
            integration_id=int_a.id,
            name="Tool A",
            namespaced_name=f"ns::tool_a_{uuid4().hex[:6]}",
            created_by=test_user.id,
        )
        tool_b = Tool(
            integration_id=int_b.id,
            name="Tool B",
            namespaced_name=f"ns::tool_b_{uuid4().hex[:6]}",
            created_by=test_user.id,
        )
        test_db_session.add_all([tool_a, tool_b])
        await test_db_session.commit()

        await test_db_session.delete(int_a)
        await test_db_session.commit()

        remaining_a = (await test_db_session.exec(select(Tool).where(Tool.id == tool_a.id))).one_or_none()
        assert remaining_a is None

        reloaded_b = (await test_db_session.exec(select(Tool).where(Tool.id == tool_b.id))).one()
        assert reloaded_b.integration_id == int_b.id


class TestIntegrationNameUniqueness:
    """Tests for DB-enforced name uniqueness on non-deleted integrations."""

    async def test_duplicate_name_raises_integrity_error(
        self,
        test_db_session: AsyncSession,
        test_user: User,
    ) -> None:
        """Creating two non-deleted integrations with the same name raises IntegrityError."""
        shared_name = f"dup-{uuid4().hex[:8]}"
        int1 = Integration(
            name=shared_name,
            integration_type=IntegrationType.MCP_SERVER,
            configuration=MCPServerConfiguration(
                integration_type="mcp_server",
                base_url="https://mcp.example.com",
            ),
            created_by=test_user.id,
            updated_by=test_user.id,
        )
        test_db_session.add(int1)
        await test_db_session.commit()

        int2 = Integration(
            name=shared_name,
            integration_type=IntegrationType.MCP_SERVER,
            configuration=MCPServerConfiguration(
                integration_type="mcp_server",
                base_url="https://mcp2.example.com",
            ),
            created_by=test_user.id,
            updated_by=test_user.id,
        )
        test_db_session.add(int2)

        with pytest.raises(IntegrityError):
            await test_db_session.commit()
        await test_db_session.rollback()

    async def test_same_name_allowed_after_delete(
        self,
        test_db_session: AsyncSession,
        test_user: User,
        integration_factory: IntegrationFactory,
    ) -> None:
        """A name can be reused after the original integration is deleted."""
        shared_name = f"reuse-{uuid4().hex[:8]}"
        int1 = await integration_factory.create(name=shared_name)
        await test_db_session.commit()

        await test_db_session.delete(int1)
        await test_db_session.flush()

        int2 = await integration_factory.create(name=shared_name)
        await test_db_session.commit()

        assert int2.name == shared_name

    async def test_unique_names_allowed(
        self,
        test_db_session: AsyncSession,
        integration_factory: IntegrationFactory,
    ) -> None:
        """Two integrations with distinct names can coexist."""
        int_a = await integration_factory.create(name=f"alpha-{uuid4().hex[:8]}")
        int_b = await integration_factory.create(name=f"beta-{uuid4().hex[:8]}")
        await test_db_session.commit()

        assert int_a.id != int_b.id
