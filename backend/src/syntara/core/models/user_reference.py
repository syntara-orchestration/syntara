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

DEFAULT_USER_REFERENCE_FIELDS: tuple[str, ...] = ("created_by", "updated_by")


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


class UserReferenceFieldsMixin:
    """Mixin for API Read schemas whose audit fields carry a :class:`UserReference`.

    Declares which fields hold a user reference (``USER_REFERENCE_FIELDS``) so that
    a single resolver can enrich them without every call site restating the names,
    and injects the matching OpenAPI metadata so the spec advertises
    ``UserReference | null`` rather than the raw ``UserReference | UUID | str``
    union the annotation would otherwise produce.

    Mix in *before* the schema's own base so this hook wins the MRO and can still
    delegate to the base implementation (e.g. ``BaseResource``'s field extras).
    """

    USER_REFERENCE_FIELDS: ClassVar[tuple[str, ...]] = DEFAULT_USER_REFERENCE_FIELDS

    @classmethod
    def __get_pydantic_json_schema__(
        cls, core_schema: PydanticCoreSchema, handler: GetJsonSchemaHandler
    ) -> JsonSchemaValue:
        """Advertise the declared user-reference fields as ``UserReference | null``."""
        parent = super().__get_pydantic_json_schema__  # type: ignore[misc]
        json_schema = parent(core_schema, handler)
        json_schema = handler.resolve_ref_schema(json_schema)
        props = json_schema.get("properties", {})
        for field in cls.USER_REFERENCE_FIELDS:
            if field not in props:
                continue
            # Replace rather than merge: a base class may have described the field
            # as a raw UUID (readOnly + a UUID ``example``), which would otherwise
            # survive alongside the UserReference ref and contradict it.
            described = {k: v for k, v in props[field].items() if k in ("title", "description")}
            props[field] = {**described, **UserReference.OPENAPI_NULLABLE_FIELD}
        return json_schema
