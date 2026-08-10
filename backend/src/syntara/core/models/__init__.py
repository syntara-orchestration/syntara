"""SQLModel base classes for shared API resources.

This module contains the core SQLModel classes that define the foundation
for all API resources in the Nexus platform.
"""

from syntara.core.models.group import Group, user_groups
from syntara.core.models.principal import (
    Principal,
    PrincipalType,
)
from syntara.core.models.secret import EncryptedSecret, Secret
from syntara.core.models.user import User
from syntara.core.models.user_identity import UserIdentity
from syntara.core.models.user_reference import UserReference

__all__ = [
    "EncryptedSecret",
    "Group",
    "Principal",
    "PrincipalType",
    "Secret",
    "User",
    "UserIdentity",
    "UserReference",
    "user_groups",
]
