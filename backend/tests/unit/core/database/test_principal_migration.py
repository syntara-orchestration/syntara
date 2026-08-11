"""Tests for UserOwnedResource → principals FK consistency.

Historically this imported ``_OWNED_TABLES`` from the principals Alembic revision
to ensure new owned tables were retargeted. That revision was removed when
migrations were flattened to a single baseline; the invariant now lives on the
models (``created_by`` / ``updated_by`` → ``principals.id``).
"""

from typing import Any

from syntara.core.database.migrations.models import ALL_MODELS  # noqa: F401
from syntara.core.models.base.user_owned import UserOwnedResource


def _concrete_user_owned_subclasses() -> list[type[Any]]:
    concrete: list[type[Any]] = []
    queue: list[type[Any]] = list(UserOwnedResource.__subclasses__())
    while queue:
        cls = queue.pop()
        tablename = getattr(cls, "__tablename__", None)
        if (
            isinstance(tablename, str)
            and getattr(cls, "__table__", None) is not None
            and not tablename.startswith("mock_")
        ):
            concrete.append(cls)
        queue.extend(cls.__subclasses__())
    return concrete


def test_user_owned_resources_fk_to_principals() -> None:
    """Every concrete UserOwnedResource must FK created_by/updated_by to principals.id.

    If this fails, a new UserOwnedResource subclass was added with the wrong FK
    target (e.g. users.id instead of principals.id).
    """
    failures: list[str] = []
    for cls in _concrete_user_owned_subclasses():
        table = getattr(cls, "__table__", None)
        tablename = getattr(cls, "__tablename__", None)
        assert table is not None
        assert isinstance(tablename, str)
        for col_name in ("created_by", "updated_by"):
            targets = {(fk.column.table.name, fk.column.name) for fk in table.c[col_name].foreign_keys}
            if ("principals", "id") not in targets:
                failures.append(f"{tablename}.{col_name} → {targets or 'no FK'}")

    assert not failures, f"UserOwnedResource ownership columns must reference principals.id. Bad columns: {failures}"
