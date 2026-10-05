"""A client library for accessing Syntara API"""

from .client import AuthenticatedClient, Client
from .filters import OPERATORS, FilterError, build_filters

__all__ = (
    "AuthenticatedClient",
    "Client",
    "build_filters",
    "FilterError",
    "OPERATORS",
)
