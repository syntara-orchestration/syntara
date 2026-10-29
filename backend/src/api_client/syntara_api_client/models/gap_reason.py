from enum import Enum


class GapReason(str, Enum):
    BELOW_AUTHORIZED_BOUNDARY = "below_authorized_boundary"
    INITIALIZATION_HISTORY_UNAVAILABLE = "initialization_history_unavailable"
    INITIAL_METADATA_MISSING = "initial_metadata_missing"
    MISSING_COMMIT = "missing_commit"
    OUT_OF_RANGE = "out_of_range"
    SOURCE_RECREATED = "source_recreated"

    def __str__(self) -> str:
        return str(self.value)
