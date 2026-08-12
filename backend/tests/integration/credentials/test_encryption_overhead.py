"""Suite 22 — Credential Storage: Encryption Overhead KPI (22.3).

Test 22.3: Encrypt/decrypt cycle for credentials with varying field
    counts (2-10 fields per credential)
    KPI: Encryption Overhead (p95) < 10ms per credential (all fields)
    MetricType: Component-level timing
    Validation:
        Measure time in SecretEncryptor.encrypt_fields() / .decrypt_fields()

This test exercises the encryption layer directly (no network I/O)
to isolate the cryptographic overhead from API latency.

Run with:
    make test-integration-coverage
"""

from __future__ import annotations

import os
import time
from typing import TYPE_CHECKING
from uuid import uuid4

import pytest

from syntara.core.lib.encryption import KEY_SIZE, SecretEncryptor
from tests.integration.helpers.perf import compute_percentile

if TYPE_CHECKING:
    from collections.abc import Callable


CREDENTIALS_PER_FIELD_COUNT = 50
FIELD_COUNTS = range(2, 11)  # 2, 3, 4, … 10
TARGET_ENCRYPTION_OVERHEAD_P95_MS = 10


_FIELD_GENERATORS: list[tuple[str, Callable[[], str]]] = [
    ("token", lambda: f"sk-perf-test-{uuid4().hex}"),
    ("host", lambda: f"https://api-{uuid4().hex[:8]}.example.com/v1"),
    ("username", lambda: f"perf-user-{uuid4().hex[:8]}"),
    ("password", lambda: f"perf-pass-{uuid4().hex}"),
    ("api_key", lambda: f"key-{uuid4().hex}-{uuid4().hex}"),
    ("base_url", lambda: f"https://provider-{uuid4().hex[:8]}.example.com/api/v2"),
    (
        "ssh_private_key",
        # Component test: synthetic keys are sufficient for testing encryption overhead
        lambda: "-----BEGIN OPENSSH PRIVATE KEY-----\n" + uuid4().hex * 4 + "\n-----END OPENSSH PRIVATE KEY-----",
    ),
    ("client_id", lambda: f"client-{uuid4().hex}"),
    ("client_secret", lambda: f"secret-{uuid4().hex}-{uuid4().hex}"),
]


def _generate_fields(n: int) -> dict[str, str]:
    """Generate *n* credential fields with realistic value sizes."""
    fields: dict[str, str] = {}
    for i in range(n):
        if i < len(_FIELD_GENERATORS):
            name, generator = _FIELD_GENERATORS[i]
            fields[name] = generator()
        else:
            fields[f"extra_field_{i}"] = f"value-{uuid4().hex}"
    return fields


class TestEncryptionOverhead:
    """22.3 — Encrypt/decrypt cycle with 2-10 fields per credential.

    Creates a SecretEncryptor with a random AES-256 key and measures
    the wall-clock time for a full encrypt_fields + decrypt_fields
    round-trip across varying field counts. Validates:
        - p95 round-trip time < 10ms per credential for every field count
        - Aggregated p95 across all field counts < 10ms
    """

    @pytest.fixture(autouse=True)
    def _encryptor(self) -> None:
        self._enc = SecretEncryptor(os.urandom(KEY_SIZE))

    def test_encrypt_decrypt_cycle_p95(self) -> None:
        """Encrypt+decrypt cycle p95 must be < 10ms for 2-10 fields."""
        all_durations: list[float] = []
        per_field_count_results: dict[int, dict[str, float]] = {}

        for field_count in FIELD_COUNTS:
            durations: list[float] = []

            for _ in range(CREDENTIALS_PER_FIELD_COUNT):
                secret_id = str(uuid4())
                fields = _generate_fields(field_count)

                start = time.monotonic()
                encrypted = self._enc.encrypt_fields(fields, secret_id)
                decrypted = self._enc.decrypt_fields(encrypted, secret_id)
                elapsed_ms = (time.monotonic() - start) * 1000

                assert decrypted == fields, "Round-trip mismatch — decrypted values differ"
                durations.append(elapsed_ms)

            p95 = compute_percentile(durations, 95)
            p50 = compute_percentile(durations, 50)
            per_field_count_results[field_count] = {"p50": p50, "p95": p95}
            all_durations.extend(durations)

        overall_p95 = compute_percentile(all_durations, 95)
        overall_p50 = compute_percentile(all_durations, 50)

        diag_parts = [
            "\n--- Encryption overhead results (22.3) ---",
            f"  credentials_per_field_count={CREDENTIALS_PER_FIELD_COUNT}",
            f"  total_cycles={len(all_durations)}",
            f"  overall: p50={overall_p50:.3f}ms, p95={overall_p95:.3f}ms",
        ]
        failures: list[str] = []
        for fc in FIELD_COUNTS:
            stats = per_field_count_results[fc]
            diag_parts.append(f"  {fc:2d} fields: p50={stats['p50']:.3f}ms, p95={stats['p95']:.3f}ms")
            if stats["p95"] >= TARGET_ENCRYPTION_OVERHEAD_P95_MS:
                failures.append(f"{fc} fields: p95={stats['p95']:.3f}ms")
        diag = "\n".join(diag_parts) + "\n"

        assert not failures, (
            f"Encryption overhead p95 exceeded {TARGET_ENCRYPTION_OVERHEAD_P95_MS}ms for: {'; '.join(failures)}{diag}"
        )
        assert overall_p95 < TARGET_ENCRYPTION_OVERHEAD_P95_MS, (
            f"Overall encryption overhead p95 {overall_p95:.3f}ms exceeds "
            f"target {TARGET_ENCRYPTION_OVERHEAD_P95_MS}ms{diag}"
        )
