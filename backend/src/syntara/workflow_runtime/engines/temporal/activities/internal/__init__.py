"""Internal workflow activities.

These activities are used internally by the workflow engine and are not
directly exposed to users.
"""

from .activity_monitoring import register_activity_monitoring

__all__ = ["register_activity_monitoring"]
