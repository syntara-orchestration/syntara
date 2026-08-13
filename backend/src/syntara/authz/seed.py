"""Seed built-in authz data (groups, default project, admin user).

Built-in roles and policies are no longer stored in the database — they
live in ``role_conventions.py`` and are resolved at runtime.  This seeder
only creates groups, the default project, the admin user, and role
assignments (which reference roles by name).
"""

from pathlib import Path
from uuid import UUID, uuid4

import structlog
from sqlalchemy import insert
from sqlalchemy.exc import IntegrityError
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.authz.models import RoleAssignment
from syntara.authz.models.project import Project
from syntara.core.config.base import get_settings
from syntara.core.models import User
from syntara.core.models.group import Group, user_groups

logger = structlog.stdlib.get_logger(__name__)

BOOTSTRAP_ADMIN_USERNAME = "admin"
BOOTSTRAP_ADMIN_FIRST_NAME = "Administrator"
# Placeholder only — operators should change this after install (self email update is allowed).
BOOTSTRAP_ADMIN_EMAIL = "admin@example.com"


def _is_duplicate_email_error(exc: IntegrityError) -> bool:
    """Return True when IntegrityError is the users.email unique constraint."""
    error_str = str(exc)
    return "ix_users_email_unique" in error_str or "Key (email)" in error_str


async def try_set_bootstrap_admin_email(session: AsyncSession, admin_user: User) -> bool:
    """Set ``BOOTSTRAP_ADMIN_EMAIL`` on the admin user when the address is free.

    Uses a savepoint so a unique-constraint conflict does not abort the outer
    seed / password-sync transaction. On conflict, leaves ``admin_user.email``
    unchanged and logs a warning.

    Returns:
        True if the placeholder email was assigned, False if it was left alone.

    """
    previous = admin_user.email
    admin_user.email = BOOTSTRAP_ADMIN_EMAIL
    try:
        async with session.begin_nested():
            await session.flush()
    except IntegrityError as exc:
        if not _is_duplicate_email_error(exc):
            raise
        admin_user.email = previous
        logger.warning(
            "Bootstrap admin placeholder email already in use; leaving admin email unchanged",
            email=BOOTSTRAP_ADMIN_EMAIL,
            user_id=str(admin_user.id),
        )
        return False
    return True


async def seed_groups_project_admin(session: AsyncSession) -> None:
    """Seed built-in groups, default project, and admin user.

    Role assignments reference roles by name — no role rows need to
    exist in the database.
    """
    (
        auth_group,
        admin_group,
        auditors_group,
        users_group,
        default_project,
        _system_project,
    ) = await _seed_groups_and_project(session)
    await session.flush()
    await _seed_assignments_and_admin(session, auth_group, admin_group, auditors_group, users_group, default_project)
    await session.commit()


async def seed_authz_data(session: AsyncSession) -> None:
    """Seed all built-in authz data into the database.

    This is the entry point used by tests after table truncation.
    """
    (
        auth_group,
        admin_group,
        auditors_group,
        users_group,
        default_project,
        _system_project,
    ) = await _seed_groups_and_project(session)
    await session.flush()
    await _seed_assignments_and_admin(session, auth_group, admin_group, auditors_group, users_group, default_project)
    await session.commit()


async def _seed_groups_and_project(
    session: AsyncSession,
) -> tuple[Group, Group, Group, Group, Project, Project]:
    """Seed default project, system project, and all built-in groups.

    Returns (auth_group, admin_group, auditors_group, users_group, default_project, system_project).
    """
    existing_proj = await session.exec(
        select(Project).where(
            Project.name == "default",
            Project.deleted_at.is_(None),  # type: ignore[union-attr]
        )
    )
    default_project = existing_proj.one_or_none()
    if not default_project:
        default_project = Project(id=uuid4(), name="default", description="Default project", is_default=True, labels={})
        session.add(default_project)

    from syntara.workflows.constants import BUILTIN_PROJECT_NAME  # noqa: PLC0415

    existing_system = await session.exec(
        select(Project).where(
            Project.name == BUILTIN_PROJECT_NAME,
            Project.deleted_at.is_(None),  # type: ignore[union-attr]
        )
    )
    system_project = existing_system.one_or_none()
    if not system_project:
        system_project = Project(
            id=uuid4(),
            name=BUILTIN_PROJECT_NAME,
            description="Default project for built-in workflows",
            is_builtin=True,
            labels={},
        )
        session.add(system_project)

    existing_auth = await session.exec(select(Group).where(Group.name == "authenticated"))
    auth_group = existing_auth.one_or_none()
    if not auth_group:
        auth_group = Group(
            id=uuid4(),
            name="authenticated",
            description="Implicit group for all authenticated users.",
            is_builtin=True,
            labels={},
        )
        session.add(auth_group)

    existing_admins = await session.exec(select(Group).where(Group.name == "admins"))
    admin_group = existing_admins.one_or_none()
    if not admin_group:
        admin_group = Group(
            id=uuid4(),
            name="admins",
            description="System administrators.",
            is_builtin=True,
            labels={},
        )
        session.add(admin_group)

    existing_auditors = await session.exec(select(Group).where(Group.name == "auditors"))
    auditors_group = existing_auditors.one_or_none()
    if not auditors_group:
        auditors_group = Group(
            id=uuid4(),
            name="auditors",
            description="Read-only access with audit log visibility.",
            is_builtin=True,
            labels={},
        )
        session.add(auditors_group)

    existing_users = await session.exec(select(Group).where(Group.name == "users"))
    users_group = existing_users.one_or_none()
    if not users_group:
        users_group = Group(
            id=uuid4(),
            name="users",
            description="Default group for local users.",
            is_builtin=True,
            labels={},
        )
        session.add(users_group)

    return auth_group, admin_group, auditors_group, users_group, default_project, system_project


async def _ensure_role_assignment(
    session: AsyncSession,
    group: Group,
    role_name: str,
    *,
    is_builtin: bool = True,
    project_id: UUID | None = None,
) -> None:
    """Create a group role assignment if it doesn't already exist."""
    where_clauses = [
        RoleAssignment.group_id == group.id,
        RoleAssignment.role_name == role_name,
    ]
    if project_id is None:
        where_clauses.append(RoleAssignment.project_id.is_(None))  # type: ignore[union-attr]
    else:
        where_clauses.append(RoleAssignment.project_id == project_id)

    existing = await session.exec(select(RoleAssignment).where(*where_clauses))
    if not existing.one_or_none():
        session.add(
            RoleAssignment(
                id=uuid4(),
                group_id=group.id,
                role_name=role_name,
                project_id=project_id,
                is_builtin=is_builtin,
                labels={},
            )
        )


async def _ensure_group_membership(session: AsyncSession, user: User, group: Group) -> None:
    """Add a user to a group if not already a member."""
    existing = await session.exec(
        select(user_groups.c.user_id).where(
            user_groups.c.user_id == user.id,
            user_groups.c.group_id == group.id,
        )
    )
    if not existing.one_or_none():
        await session.exec(insert(user_groups).values(user_id=user.id, group_id=group.id))


async def _seed_assignments_and_admin(
    session: AsyncSession,
    auth_group: Group,
    admin_group: Group,
    auditors_group: Group,
    users_group: Group,
    default_project: Project,
) -> None:
    """Seed group-role assignments and bootstrap admin user."""
    await _ensure_role_assignment(session, auth_group, "authenticated")
    await _ensure_role_assignment(session, users_group, "user")
    await _ensure_role_assignment(session, admin_group, "admin")
    await _ensure_role_assignment(session, auditors_group, "auditor")
    await _ensure_role_assignment(session, users_group, "project-user", is_builtin=False, project_id=default_project.id)

    # Seed service principals for internal mTLS-authenticated services
    from syntara.core.models.principal import KNOWN_SERVICE_CNS, Principal, service_principal_id  # noqa: PLC0415

    for cn in KNOWN_SERVICE_CNS:
        sp_id = service_principal_id(cn)
        existing = await session.get(Principal, sp_id)
        if not existing:
            session.add(Principal.for_service(cn))
            await session.flush()
            logger.info("Service principal created", cn=cn, principal_id=str(sp_id))

    # Bootstrap admin user
    existing_admin_user = await session.exec(select(User).where(User.username == BOOTSTRAP_ADMIN_USERNAME))
    admin_user = existing_admin_user.one_or_none()
    if not admin_user:
        password_hash = _read_admin_password_hash()
        # Assign placeholder email after insert so a taken address cannot fail create.
        admin_user = User(
            id=uuid4(),
            username=BOOTSTRAP_ADMIN_USERNAME,
            first_name=BOOTSTRAP_ADMIN_FIRST_NAME,
            email=None,
            is_enabled=True,
            is_builtin=True,
            password_hash=password_hash,
        )
        session.add(admin_user)
        await session.flush()
        await try_set_bootstrap_admin_email(session, admin_user)
        logger.info("Bootstrap admin user created", user_id=str(admin_user.id), email=admin_user.email)
    elif admin_user.email is None:
        # Existing installs seeded before AAP-87627 had email=NULL in JWTs.
        if await try_set_bootstrap_admin_email(session, admin_user):
            logger.info(
                "Backfilled bootstrap admin email placeholder",
                user_id=str(admin_user.id),
                email=BOOTSTRAP_ADMIN_EMAIL,
            )

    await _ensure_group_membership(session, admin_user, auth_group)
    await _ensure_group_membership(session, admin_user, admin_group)
    await _ensure_group_membership(session, admin_user, users_group)

    await session.commit()


def _read_admin_password_hash() -> str | None:
    """Read the admin password from the configured file and return its hash.

    Returns ``None`` (with a warning) if the path is not configured or the
    file is empty, so that the application can still start without a
    password file — the admin user just won't be able to log in locally.
    """
    from syntara.auth.passwords import hash_password  # noqa: PLC0415

    settings = get_settings()
    password_path = settings.admin_password_path
    if not password_path:
        logger.warning(
            "APP_ADMIN_PASSWORD_PATH not set — admin user will have no password. "
            "Run 'make secrets-generate' to create one."
        )
        return None

    path = Path(password_path)
    if not path.exists():
        logger.warning("Admin password file not found", path=password_path)
        return None

    password = path.read_text().strip()
    if not password:
        logger.warning("Admin password file is empty", path=password_path)
        return None

    from syntara.auth.passwords import validate_password_complexity  # noqa: PLC0415

    try:
        validate_password_complexity(password)
    except ValueError:
        logger.warning(
            "Admin password does not meet complexity requirements"
            " — consider updating it via 'orchestrator-admin reset-password'",
            path=password_path,
        )

    return hash_password(password)
