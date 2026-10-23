from enum import Enum


class KafkaSaslMechanism(str, Enum):
    PLAIN = "PLAIN"
    SCRAM_SHA_256 = "SCRAM-SHA-256"
    SCRAM_SHA_512 = "SCRAM-SHA-512"

    def __str__(self) -> str:
        return str(self.value)
