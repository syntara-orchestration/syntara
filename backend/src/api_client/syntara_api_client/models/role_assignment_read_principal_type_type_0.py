from enum import Enum


class RoleAssignmentReadPrincipalTypeType0(str, Enum):
    GROUP = "group"
    SERVICE = "service"
    SERVICE_ACCOUNT = "service_account"
    USER = "user"

    def __str__(self) -> str:
        return str(self.value)
