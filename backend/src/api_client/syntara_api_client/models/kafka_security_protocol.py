from enum import Enum


class KafkaSecurityProtocol(str, Enum):
    PLAINTEXT = "PLAINTEXT"
    SASL_SSL = "SASL_SSL"
    SSL = "SSL"

    def __str__(self) -> str:
        return str(self.value)
