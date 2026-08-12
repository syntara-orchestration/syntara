"""Unit tests for Installation model.

Tests cover:
- Model field definitions (id, created_at)
- Table name
- SQLModel table registration
- UUID primary key
"""

import uuid

from sqlmodel import SQLModel

from syntara.core.models.installation import Installation


class TestInstallationModel:
    """Unit tests for the Installation SQLModel."""

    def test_is_sqlmodel_table(self) -> None:
        """Installation should be registered as a SQLModel table."""
        assert hasattr(Installation, "__tablename__")
        assert Installation.__tablename__ == "installation"

    def test_id_is_uuid_primary_key(self) -> None:
        """The id field should be a UUID primary key."""
        table = Installation.__table__  # type: ignore[attr-defined]
        pk_cols = [col.name for col in table.primary_key.columns]
        assert pk_cols == ["id"]

        id_col = table.columns["id"]
        assert id_col.primary_key

    def test_created_at_field_exists(self) -> None:
        """The created_at field should exist on the table."""
        table = Installation.__table__  # type: ignore[attr-defined]
        assert "created_at" in table.columns
        col = table.columns["created_at"]
        assert col.server_default is not None

    def test_model_has_only_expected_columns(self) -> None:
        """Installation table should have exactly the expected columns."""
        table = Installation.__table__  # type: ignore[attr-defined]
        column_names = {col.name for col in table.columns}
        assert column_names == {"id", "created_at", "is_singleton", "salt"}

    def test_does_not_inherit_base_resource(self) -> None:
        """Installation should NOT inherit from BaseResource (system singleton)."""
        assert Installation.__mro__[1] is SQLModel

    def test_can_create_instance(self) -> None:
        """Should be able to create an Installation instance with a UUID and salt."""
        installation_id = uuid.uuid4()
        salt = uuid.uuid4()
        installation = Installation(id=installation_id, salt=salt)
        assert installation.id == installation_id
        assert installation.salt == salt
