"""Resource composite SQLModel definition.

This module contains the Resource SQLModel class that combines all base resource
capabilities through multiple inheritance.
"""

from abc import ABC
from typing import Any, ClassVar

from syntara.core.models.base.named import NamedResource
from syntara.core.models.base.soft_deletable import SoftDeletableResource
from syntara.core.models.base.user_owned import UserOwnedResource


class Resource(NamedResource, SoftDeletableResource, UserOwnedResource, ABC):
    """Abstract complete resource SQLModel combining all base capabilities.

    This composite class inherits from all three extension models to provide
    a complete resource with naming, soft deletion, and user ownership capabilities.

    This class cannot be instantiated directly and does not create database tables.
    Concrete subclasses must inherit from this class and set table=True.

    ```
    class MyResource(Resource, table=True):
        pass
    ```

    Combined Attributes:
        From BaseResource (via all parents):
            id: UUID primary key
            created_at: Creation timestamp
            updated_at: Last update timestamp
            labels: Optional key-value metadata

        From NamedResource:
            name: Human-readable name (required, 1-255 chars)
            description: Optional detailed description (max 2000 chars)

        From SoftDeletableResource:
            deleted_at: Optional timestamp when resource was soft deleted
            deleted_by: Optional UUID of user who performed the soft delete

        From UserOwnedResource:
            created_by: UUID of user who created the resource (required)
            updated_by: Optional UUID of user who last updated the resource

    This is the recommended base SQLModel for most API resources that need
    the full set of capabilities.
    """

    # No additional fields - inherits everything from parent classes

    FIELD_SCHEMA_EXTRAS: ClassVar[dict[str, dict[str, Any]]] = {
        **NamedResource.FIELD_SCHEMA_EXTRAS,
        **SoftDeletableResource.FIELD_SCHEMA_EXTRAS,
        **UserOwnedResource.FIELD_SCHEMA_EXTRAS,
    }

    # Combine filterable fields from all parent classes (deduplicated)
    __filterable_fields__: ClassVar[list[str]] = list(
        dict.fromkeys(
            [
                *NamedResource.__filterable_fields__,
                *SoftDeletableResource.__filterable_fields__,
                *UserOwnedResource.__filterable_fields__,
            ]
        )
    )

    # Combine sortable fields from all parent classes (deduplicated)
    __sortable_fields__: ClassVar[list[str]] = list(
        dict.fromkeys(
            [
                *NamedResource.__sortable_fields__,
                *SoftDeletableResource.__sortable_fields__,
                *UserOwnedResource.__sortable_fields__,
            ]
        )
    )
