"""Base models package.

This package contains foundational model classes for the Syntara application.
"""

from syntara.core.models.base.base_resource import BaseResource
from syntara.core.models.base.named import NamedResource
from syntara.core.models.base.query_params import BaseListParams, BasePaginatedRequest
from syntara.core.models.base.resource import Resource
from syntara.core.models.base.soft_deletable import SoftDeletableResource
from syntara.core.models.base.user_owned import UserOwnedResource

__all__ = [
    "BaseListParams",
    "BasePaginatedRequest",
    "BaseResource",
    "NamedResource",
    "Resource",
    "SoftDeletableResource",
    "UserOwnedResource",
]
