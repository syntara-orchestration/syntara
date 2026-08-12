"""Base class for domain configuration models with sensitive fields.

Consumer domains (IdentityProviders, future GlobalSettings) subclass this
to declare which fields are secrets. SecretConsumerMixin uses
sensitive_fields() to know what to encrypt/mask.
"""

import warnings
from typing import ClassVar

from pydantic import ConfigDict
from sqlmodel import SQLModel


class BaseConsumerConfiguration(SQLModel):
    """Base configuration for services that consume SecretService.

    Subclasses MUST override sensitive_fields() to declare which field
    names contain secret values requiring encryption.

    This is NOT a database table — it is a schema base class.
    Domain tables store the full configuration as JSONB, with
    sensitive field values encrypted via SecretService/StorageBackend.
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")  # type: ignore[assignment]

    @classmethod
    def __pydantic_init_subclass__(cls, **kwargs: object) -> None:
        """Warn if a concrete subclass forgets to override sensitive_fields()."""
        super().__pydantic_init_subclass__(**kwargs)
        if "sensitive_fields" not in cls.__dict__:
            warnings.warn(
                f"{cls.__name__} does not override sensitive_fields() — "
                "all fields will be treated as non-sensitive (no encryption).",
                UserWarning,
                stacklevel=2,
            )

    @classmethod
    def sensitive_fields(cls) -> frozenset[str]:
        """Return the set of field names that contain secret values.

        Subclasses MUST override this method to declare their sensitive fields.
        """
        return frozenset()
