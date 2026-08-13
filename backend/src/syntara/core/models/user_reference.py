"""UserReference model for embedding user identity in API responses.

Provides a structured representation of a user (id + name snapshot) suitable
for embedding in any resource that tracks "who performed this action".
"""

from typing import ClassVar
from uuid import UUID

from pydantic import ConfigDict, GetJsonSchemaHandler
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import CoreSchema as PydanticCoreSchema
from sqlmodel import Field, SQLModel


class UserReference(SQLModel):
    """Minimal user identification for embedding in other resources.

    This model captures user identity at the time of an action, providing
    a snapshot that doesn't change even if the user's details are updated later.
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(from_attributes=True)  # type: ignore[assignment]

    id: UUID = Field(..., description="User's unique identifier")
    name: str = Field(..., description="User's display name at time of action")

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
