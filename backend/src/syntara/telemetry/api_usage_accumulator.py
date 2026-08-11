"""Thread-safe in-memory accumulator for API usage metrics.

Collects per-request caller identity and endpoint data between
periodic collector drain cycles. Each drain atomically swaps
the internal state with empty containers and returns a snapshot.

Memory is bounded by (distinct principals x distinct endpoint templates).
"""

from __future__ import annotations

import threading
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache


@dataclass(frozen=True)
class AccumulatorSnapshot:
    """Immutable snapshot returned by drain()."""

    caller_ids: frozenset[str]
    callers_by_type: dict[str, int]
    callers_by_interface: dict[str, int]
    feature_usage: dict[tuple[str, str, str], int]


class APIUsageAccumulator:
    """Thread-safe accumulator for unique caller and feature usage tracking.

    The accumulator is written to from the audit event dispatcher thread
    (synchronous) and drained from the periodic collector's async callback.
    A threading.Lock guards all mutations.
    """

    def __init__(self) -> None:
        """Initialize empty accumulator with a threading lock."""
        self._lock = threading.Lock()
        self._caller_ids: set[str] = set()
        self._callers_by_type: dict[str, set[str]] = {}
        self._callers_by_interface: dict[str, set[str]] = {}
        self._feature_usage: Counter[tuple[str, str, str]] = Counter()

    def record(
        self,
        actor_id_hash: str,
        principal_type: str,
        endpoint_template: str,
        http_method: str,
        interface: str,
    ) -> None:
        """Record a single API request for aggregation.

        Args:
            actor_id_hash: HMAC-hashed actor ID for anonymized tracking.
            principal_type: Principal type string (e.g. "user", "service_account").
            endpoint_template: Route template (e.g. "/api/v1/workflows/{workflow_id}").
            http_method: HTTP method (e.g. "GET", "POST").
            interface: Originating interface ("api" or "ui").

        """
        with self._lock:
            self._caller_ids.add(actor_id_hash)

            self._callers_by_type.setdefault(principal_type, set()).add(actor_id_hash)
            self._callers_by_interface.setdefault(interface, set()).add(actor_id_hash)

            self._feature_usage[(endpoint_template, http_method, interface)] += 1

    def drain(self) -> AccumulatorSnapshot:
        """Atomically swap internal state and return a snapshot.

        Returns:
            An immutable snapshot of all accumulated data since the last drain.

        """
        with self._lock:
            snapshot = AccumulatorSnapshot(
                caller_ids=frozenset(self._caller_ids),
                callers_by_type={k: len(v) for k, v in self._callers_by_type.items()},
                callers_by_interface={k: len(v) for k, v in self._callers_by_interface.items()},
                feature_usage=dict(self._feature_usage),
            )

            self._caller_ids = set()
            self._callers_by_type = {}
            self._callers_by_interface = {}
            self._feature_usage = Counter()

        return snapshot


@lru_cache(maxsize=1)
def get_accumulator() -> APIUsageAccumulator:
    """Return the module-level singleton accumulator."""
    return APIUsageAccumulator()
