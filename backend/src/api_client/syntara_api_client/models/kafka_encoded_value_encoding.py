from enum import Enum


class KafkaEncodedValueEncoding(str, Enum):
    BASE64 = "base64"
    UTF_8 = "utf-8"

    def __str__(self) -> str:
        return str(self.value)
