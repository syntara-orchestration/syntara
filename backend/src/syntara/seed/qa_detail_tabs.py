"""Seed disposable records for manual nested detail-tab QA."""

from sqlalchemy import insert
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.authz.models.project import Project
from syntara.core.models import Group, User, user_groups
from syntara.credentials.models.credential import Credential
from syntara.credentials.models.credential_type import CredentialType

QA_USER_NAME = "qa-nested-tabs-user"
QA_CREDENTIAL_NAME = "QA Nested Tabs Credential"
QA_CREDENTIAL_TYPE_NAME = "QA Nested Tabs Type"


async def seed_qa_detail_tabs(session: AsyncSession) -> None:
    """Create a secret-free user and credential for nested-route QA.

    The seeder is idempotent and only inserts records when they are missing.
    It depends on the standard ``authz`` seeder for the admin principal,
    default project, and ``users`` group.
    """
    admin = (await session.exec(select(User).where(User.username == "admin"))).one()
    project = (await session.exec(select(Project).where(Project.name == "default"))).one()
    users_group = (await session.exec(select(Group).where(Group.name == "users"))).one()

    credential_type = (
        await session.exec(select(CredentialType).where(CredentialType.name == QA_CREDENTIAL_TYPE_NAME))
    ).one_or_none()
    if credential_type is None:
        credential_type = CredentialType(
            name=QA_CREDENTIAL_TYPE_NAME,
            description="Empty-input type for nested detail-tab layout QA",
            inputs={"fields": [], "required": []},
            injectors={},
            managed=False,
            labels={},
        )
        session.add(credential_type)
        await session.flush()

    user = (await session.exec(select(User).where(User.username == QA_USER_NAME))).one_or_none()
    if user is None:
        user = User(
            username=QA_USER_NAME,
            email="qa-nested-tabs-user@example.invalid",
            first_name="QA Nested",
            last_name="Tabs User",
            is_enabled=True,
            is_builtin=False,
            labels={},
        )
        session.add(user)
        await session.flush()

    membership = await session.exec(
        select(user_groups.c.user_id).where(
            user_groups.c.user_id == user.id,
            user_groups.c.group_id == users_group.id,
        )
    )
    if membership.one_or_none() is None:
        await session.exec(insert(user_groups).values(user_id=user.id, group_id=users_group.id))

    credential = (
        await session.exec(
            select(Credential).where(
                Credential.name == QA_CREDENTIAL_NAME,
                Credential.project_id == project.id,
            )
        )
    ).one_or_none()
    if credential is None:
        session.add(
            Credential(
                name=QA_CREDENTIAL_NAME,
                description="Secret-free credential for nested detail-tab layout QA",
                credential_type_id=credential_type.id,
                secret_id=None,
                project_id=project.id,
                created_by=admin.id,
                updated_by=admin.id,
                labels={},
            )
        )

    await session.commit()
