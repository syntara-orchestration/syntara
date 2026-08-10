"""baseline schema

Revision ID: b69ef9067e66
Revises:
Create Date: 2026-08-06 08:26:56.628560

"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
from sqlmodel import SQLModel

from syntara.core.database.migrations.models import ALL_MODELS  # noqa: F401

# revision identifiers, used by Alembic.
revision: str = "b69ef9067e66"
down_revision: str | None = None
branch_labels: str | None = None
depends_on: str | None = None

_SQL_PATH = Path(__file__).with_suffix(".sql")
_DOLLAR_TAG = re.compile(r"\$([A-Za-z_]*)\$")


def _is_executable(statement: str) -> bool:
    return any(line.strip() and not line.lstrip().startswith("--") for line in statement.splitlines())


def _split_sql(sql: str) -> list[str]:
    """Split SQL on semicolons, respecting dollar-quoted strings."""
    stmts: list[str] = []
    buf: list[str] = []
    i = 0
    in_dollar = False
    dollar_tag = ""
    while i < len(sql):
        if not in_dollar and sql[i] == "$":
            match = _DOLLAR_TAG.match(sql, i)
            if match:
                dollar_tag = match.group(0)
                in_dollar = True
                buf.append(dollar_tag)
                i += len(dollar_tag)
                continue
        if in_dollar:
            if sql.startswith(dollar_tag, i):
                buf.append(dollar_tag)
                i += len(dollar_tag)
                in_dollar = False
                dollar_tag = ""
                continue
            buf.append(sql[i])
            i += 1
            continue
        if sql[i] == ";":
            stmt = "".join(buf).strip()
            if stmt and _is_executable(stmt):
                stmts.append(stmt)
            buf = []
            i += 1
            continue
        buf.append(sql[i])
        i += 1
    tail = "".join(buf).strip()
    if tail and _is_executable(tail):
        stmts.append(tail)
    return stmts


# Lookup rows formerly inserted by a7b8c9d0e1f2 (schema dump is DDL-only).
_SETTING_CATEGORIES: tuple[tuple[str, str, str, int], ...] = (
    ("ai_llm", "AI / LLM", "Artificial intelligence and large language model settings", 10),
    ("context_manager", "Context Manager", "Token limits, retrieval, grounding, compression, and context assembly", 20),
    ("workflow_execution", "Workflow Execution", "Workflow execution and orchestration settings", 30),
    ("integrations", "Integrations", "Third-party integration settings", 40),
    ("system", "System", "System-level settings", 50),
    ("application", "Application", "Application-level settings", 60),
)


def upgrade() -> None:
    """Create the full schema in one revision."""
    for statement in _split_sql(_SQL_PATH.read_text()):
        op.execute(sa.text(statement))

    # Singleton installation row (was inserted by the pre-flatten installation
    # migration). Telemetry requires exactly one row with id + salt.
    op.execute(sa.text("INSERT INTO installation (id, salt) VALUES (gen_random_uuid(), gen_random_uuid())"))

    # setting_categories lookup rows (was data in a7b8c9d0e1f2). The settings
    # seeder may upsert additional catalog entries after migrate.
    now = datetime.now(UTC)
    setting_categories = sa.table(
        "setting_categories",
        sa.column("id", sa.Uuid()),
        sa.column("slug", sa.String()),
        sa.column("name", sa.String()),
        sa.column("description", sa.String()),
        sa.column("display_order", sa.Integer()),
        sa.column("labels", postgresql.JSONB()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    op.bulk_insert(
        setting_categories,
        [
            {
                "id": uuid4(),
                "slug": slug,
                "name": name,
                "description": description,
                "display_order": display_order,
                "labels": {},
                "created_at": now,
                "updated_at": now,
            }
            for slug, name, description, display_order in _SETTING_CATEGORIES
        ],
    )


# PL/pgSQL helpers and enums created by this baseline (not extension-owned).
_OWNED_FUNCTIONS: tuple[str, ...] = (
    "audit_triggers_status()",
    "audit_triggers_enable()",
    "audit_triggers_disable()",
    "audit_trigger_enable(text)",
    "audit_trigger_disable(text)",
    "audit_crud_operation()",
    "_build_resource_snapshot(jsonb, text, text[])",
    "_build_changes(jsonb, jsonb, text, text[])",
    "uuid_generate_v7()",
)

_OWNED_ENUMS: tuple[str, ...] = (
    "activitystatus",
    "approvalrequeststatus",
    "auditeventsource",
    "countertype",
    "executionmode",
    "filestatus",
    "integration_refresh_status",
    "integration_scope",
    "integration_status",
    "integration_type",
    "invocationstatus",
    "nodetype",
    "publishaction",
    "settingvaluetype",
    "targettype",
    "tool_parameter_type",
    "tool_status",
    "toolexecutionstatus",
    "userrole",
    "windowduration",
    "workflowexecutionstatus",
)


def downgrade() -> None:
    """Remove only application-owned objects (not everything in ``public``).

    Do not ``DROP SCHEMA`` and do not delete arbitrary customer objects that
    happen to live in ``public``. Drop tables registered on SQLModel metadata
    for this app, then the baseline's audit helpers / enums. Leave
    ``alembic_version`` for Alembic bookkeeping.
    """
    for table_name in sorted(SQLModel.metadata.tables):
        op.execute(sa.text(f'DROP TABLE IF EXISTS public."{table_name}" CASCADE'))

    for func_sig in _OWNED_FUNCTIONS:
        op.execute(sa.text(f"DROP FUNCTION IF EXISTS public.{func_sig} CASCADE"))

    for enum_name in _OWNED_ENUMS:
        op.execute(sa.text(f'DROP TYPE IF EXISTS public."{enum_name}" CASCADE'))
