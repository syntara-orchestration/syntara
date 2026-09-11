"""Domain exceptions for credential management."""

from syntara.core.exception_registry import fastapi_exception
from syntara.core.exceptions import SyntaraError


@fastapi_exception(handler="syntara.credentials.error_handlers.credential_error_handler")
class CredentialError(SyntaraError):
    """Base exception for all credential management errors."""


@fastapi_exception(handler="syntara.credentials.error_handlers.credential_not_found_handler")
class CredentialNotFoundError(CredentialError):
    """Exception raised when a credential is not found."""


@fastapi_exception(handler="syntara.credentials.error_handlers.credential_name_conflict_handler")
class CredentialNameConflictError(CredentialError):
    """Exception raised when a credential name already exists."""

    def __init__(self, name: str) -> None:
        """Initialize exception with credential name."""
        self.name = name
        super().__init__(f"Credential with name '{name}' already exists in this project")


@fastapi_exception(handler="syntara.credentials.error_handlers.credential_validation_error_handler")
class CredentialValidationError(CredentialError):
    """Exception raised for credential input validation errors."""


@fastapi_exception(handler="syntara.credentials.error_handlers.credential_decryption_error_handler")
class CredentialDecryptionError(CredentialError):
    """Exception raised when credential decryption fails."""


@fastapi_exception(handler="syntara.credentials.error_handlers.credential_disabled_error_handler")
class CredentialDisabledError(CredentialError):
    """Exception raised when a disabled credential is used in an operation."""

    def __init__(self, name: str) -> None:
        """Initialize with credential name."""
        self.name = name
        super().__init__(f"Credential '{name}' is disabled. Re-enable it to continue.")


@fastapi_exception(handler="syntara.credentials.error_handlers.credential_in_use_error_handler")
class CredentialInUseError(CredentialError):
    """Exception raised when deleting a credential still used as an integration's management credential.

    Previously the delete silently nulled the integration's
    management_credential_id, leaving validation_status stale (e.g. still
    "available") with no indication the integration could no longer
    authenticate. Blocking the delete forces the caller to detach the
    credential from all referencing integrations first.
    """

    def __init__(self, name: str, integration_names: list[str], total_count: int) -> None:
        """Initialize with credential name and a sample of referencing integration names.

        integration_names may legitimately be empty relative to a positive
        total_count in the rare "double-race" case (an integration reference
        detected the reference right after a TOCTOU-triggered IntegrityError,
        but was itself gone by the time names were re-queried). Falls back to
        generic wording rather than rendering an empty or misleading name list.
        """
        self.name = name
        self.integration_names = integration_names
        self.total_count = total_count

        plural = "s" if total_count != 1 else ""
        if integration_names:
            shown = ", ".join(f"'{n}'" for n in integration_names)
            remaining = total_count - len(integration_names)
            suffix = f" and {remaining} more" if remaining > 0 else ""
            where = f" ({shown}{suffix})"
        else:
            where = ""
        super().__init__(
            f"Cannot delete credential '{name}': still in use by {total_count} "
            f"integration{plural}{where}. Remove the credential from "
            "these integrations before deleting it."
        )


@fastapi_exception(handler="syntara.credentials.error_handlers.project_credential_in_use_error_handler")
class ProjectCredentialInUseError(CredentialError):
    """Raised when a project cannot be deleted because its credentials are still used by integrations.

    Integrations are not project-scoped (global LLM/MCP/AAP integrations
    routinely reference a project credential via management_credential_id).
    The ON DELETE RESTRICT FK makes the database reject the cascade, so
    the project service must check upfront and surface an actionable 409
    instead of a generic constraint error.
    """

    def __init__(
        self,
        project_name: str,
        credential_names: list[str],
        integration_names: list[str],
        total_integration_count: int,
    ) -> None:
        """Initialize with project name and samples of referenced credentials/integrations."""
        self.project_name = project_name
        self.credential_names = credential_names
        self.integration_names = integration_names
        self.total_integration_count = total_integration_count

        int_plural = "s" if total_integration_count != 1 else ""
        if integration_names:
            shown = ", ".join(f"'{n}'" for n in integration_names)
            remaining = total_integration_count - len(integration_names)
            suffix = f" and {remaining} more" if remaining > 0 else ""
            int_list = f" ({shown}{suffix})"
        else:
            int_list = ""

        cred_shown = ", ".join(f"'{n}'" for n in credential_names[:5])
        cred_remaining = len(credential_names) - 5
        cred_suffix = f" and {cred_remaining} more" if cred_remaining > 0 else ""
        cred_list = f"{cred_shown}{cred_suffix}"

        super().__init__(
            f"Cannot delete project '{project_name}': {total_integration_count} "
            f"integration{int_plural}{int_list} still reference credentials "
            f"in this project ({cred_list}). Detach or reassign these "
            f"integrations before deleting the project."
        )
