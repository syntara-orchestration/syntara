"""Type variables for service generics.

This module defines type variables used for generic type hints in service classes.
"""

# Type variables for BaseResource types and ResourcesResponse types
from typing import TYPE_CHECKING, Any, TypeVar

if TYPE_CHECKING:
    from syntara.core.models.base import BaseResource
    from syntara.core.models.pagination import ResourcesResponse

TModel = TypeVar("TModel", bound="BaseResource")
TResponse = TypeVar("TResponse", bound="ResourcesResponse[Any]")
