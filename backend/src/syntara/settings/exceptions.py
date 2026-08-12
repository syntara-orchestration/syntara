"""Domain exceptions for runtime settings."""

from syntara.core.exception_registry import fastapi_exception
from syntara.core.exceptions import NexusError


class SettingError(NexusError):
    """Base exception for all settings errors."""


@fastapi_exception(handler="syntara.settings.error_handlers.setting_not_found_handler")
class SettingNotFoundError(SettingError):
    """Raised when a setting key does not exist."""

    def __init__(self, key: str) -> None:
        """Initialise with the missing setting key.

        Args:
            key: Dot-namespaced setting key that was not found.

        """
        self.key = key
        super().__init__(f"Setting '{key}' not found")


@fastapi_exception(handler="syntara.settings.error_handlers.optimistic_lock_error_handler")
class OptimisticLockError(SettingError):
    """Raised when a write is rejected due to a version mismatch.

    Callers should re-fetch the setting, inspect the current value, and
    resubmit with the updated version if the change is still appropriate.

    """

    def __init__(self, key: str, current_version: int, submitted_version: int) -> None:
        """Initialise with conflict details.

        Args:
            key: Setting key that caused the conflict.
            current_version: Version stored in the database.
            submitted_version: Version submitted by the caller.

        """
        self.key = key
        self.current_version = current_version
        self.submitted_version = submitted_version
        super().__init__(f"Setting '{key}' version conflict: current={current_version}, submitted={submitted_version}")


@fastapi_exception(handler="syntara.settings.error_handlers.setting_type_error_handler")
class SettingTypeError(SettingError):
    """Raised when a setting value has an unexpected runtime type."""

    def __init__(self, key: str, expected: str, actual: str) -> None:
        """Initialise with the setting key, expected type, and actual type.

        Args:
            key: Setting key that returned the wrong type.
            expected: The type that was expected (e.g. ``'int'``).
            actual: The type that was actually found (e.g. ``'str'``).

        """
        self.key = key
        self.expected = expected
        self.actual = actual
        super().__init__(f"Setting '{key}' expected type {expected}, got {actual}")


@fastapi_exception(handler="syntara.settings.error_handlers.setting_validation_error_handler")
class SettingValidationError(SettingError):
    """Raised when a setting value fails type or constraint validation."""

    def __init__(self, key: str, detail: str) -> None:
        """Initialise with the setting key and a human-readable detail message.

        Args:
            key: Dot-namespaced setting key that failed validation.
            detail: Description of the validation failure.

        """
        self.key = key
        self.detail = detail
        super().__init__(f"Validation failed for setting '{key}': {detail}")
