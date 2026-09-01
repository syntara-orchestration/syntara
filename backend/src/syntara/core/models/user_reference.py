"""UserReference model for embedding user identity in API responses.

Provides a structured representation of a principal (id + current name)
suitable for embedding in any resource that tracks "who performed this
action".
"""

from typing import Any, ClassVar
from uuid import UUID

from pydantic import ConfigDict, GetJsonSchemaHandler
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import CoreSchema as PydanticCoreSchema
from sqlmodel import Field, SQLModel


class UserReference(SQLModel):
    """Minimal user identification for embedding in other resources.

    The name is resolved from the database when the response is built, not
    stored alongside the id, so it always reflects the principal's current
    name. Renaming a user therefore changes the name shown for their past
    actions.
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(from_attributes=True)  # type: ignore[assignment]

    id: UUID = Field(..., description="User's unique identifier")
    name: str = Field(..., description="Principal's current display name, resolved when the response is built")

    OPENAPI_NULLABLE_FIELD: ClassVar[dict[str, Any]] = {
        "readOnly": True,
        "anyOf": [
            {"$ref": "#/components/schemas/UserReference"},
            {"type": "null"},
        ],
    }

    @classmethod
    def __get_pydantic_json_schema__(
        cls, core_schema: PydanticCoreSchema, handler: GetJsonSchemaHandler
    ) -> JsonSchemaValue:
        """Strip auto-generated ``title`` from properties to match the OpenAPI spec."""
        json_schema = handler(core_schema)
        json_schema = handler.resolve_ref_schema(json_schema)
        for prop in json_schema.get("properties", {}).values():
            prop.pop("title", None)
        return json_schema
