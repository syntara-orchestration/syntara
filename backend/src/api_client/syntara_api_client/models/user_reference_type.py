from enum import Enum


class UserReferenceType(str, Enum):
    DELETED_SERVICE_ACCOUNT = "deleted_service_account"
    DELETED_USER = "deleted_user"
    SERVICE = "service"
    SERVICE_ACCOUNT = "service_account"
    SYSTEM = "system"
    USER = "user"

    def __str__(self) -> str:
        return str(self.value)
