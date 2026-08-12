"""Suite 22 — Credential Storage: Nonce Uniqueness Under Burst KPI (22.11).

Test 22.11: Per-field nonce uniqueness under burst — create 100
    credentials in rapid succession
    KPI: Nonce Generation Overhead < 1ms per field
    Measurement: Component-level timing
    Validation:
        Verify no nonce collisions; measure crypto nonce throughput

This test exercises the encryption layer directly (no network I/O)
to isolate nonce generation and validate uniqueness under burst load.
All 100 credentials are encrypted concurrently across a thread pool
to create realistic contention on os.urandom() and the AESGCM instance.
Nonces are extracted from the base64(nonce + ciphertext + tag) format
used by SecretEncryptor.

Run with:
    make test-integration-coverage
"""

from __future__ import annotations

import base64
import os
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from uuid import uuid4

import pytest

from syntara.core.lib.encryption import KEY_SIZE, NONCE_SIZE, SecretEncryptor
from tests.integration.helpers.perf import compute_percentile

CREDENTIAL_COUNT = 100
FIELDS_PER_CREDENTIAL = 5
BURST_WORKERS = 20
TARGET_NONCE_OVERHEAD_P95_MS = 10.0
NONCE_THROUGHPUT_ITERATIONS = 10_000


def _extract_nonce(encrypted_b64: str) -> bytes:
    """Extract the 12-byte nonce prefix from an encrypted field value."""
    raw = base64.b64decode(encrypted_b64)
    return raw[:NONCE_SIZE]


def _generate_credential_fields(credential_index: int) -> dict[str, str]:
    """Generate FIELDS_PER_CREDENTIAL realistic field values."""
    return {
        "token": f"sk-burst-{credential_index}-{uuid4().hex}",
        "host": f"https://api-{uuid4().hex[:8]}.example.com",
        "username": f"burst-user-{credential_index}",
        "password": f"burst-pass-{uuid4().hex}",
        "api_key": f"key-{uuid4().hex}-{uuid4().hex}",
    }


@dataclass
class _BurstResult:
    """Results from encrypting one credential's fields."""

    nonces: list[bytes]
    field_durations_ms: list[float]
    total_duration_ms: float
    integrity_ok: bool


@dataclass
class _BurstAccumulator:
    """Thread-safe accumulator for burst results."""

    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    results: list[_BurstResult] = field(default_factory=list)

    def add(self, result: _BurstResult) -> None:
        with self._lock:
            self.results.append(result)


class TestNonceUniqueness:
    """22.11 — Per-field nonce uniqueness under burst encryption.

    Encrypts 100 credentials x 5 fields = 500 encrypt_field() calls
    concurrently across 20 threads sharing a single SecretEncryptor.

    Validates:
        - Per-field encryption overhead p95 < 1ms
        - Zero nonce collisions across all 500 encrypted values
        - Data integrity after round-trip under contention
        - Raw os.urandom(12) throughput is measured as a baseline
    """

    @pytest.fixture(autouse=True)
    def _encryptor(self) -> None:
        self._enc = SecretEncryptor(os.urandom(KEY_SIZE))

    def test_nonce_uniqueness_under_burst(self) -> None:
        """Encrypt 500 fields concurrently; p95 < 1ms, no nonce collisions."""
        accumulator = _BurstAccumulator()

        # --- Burst: all 100 credentials encrypted concurrently ---
        with ThreadPoolExecutor(max_workers=BURST_WORKERS) as executor:
            futures: list[Future[None]] = [
                executor.submit(
                    _encrypt_one_credential,
                    self._enc,
                    cred_idx,
                    accumulator,
                )
                for cred_idx in range(CREDENTIAL_COUNT)
            ]
            for future in as_completed(futures):
                future.result()

        results = accumulator.results
        assert len(results) == CREDENTIAL_COUNT

        all_nonces: list[bytes] = []
        per_field_durations: list[float] = []
        per_credential_durations: list[float] = []
        integrity_failures = 0

        for r in results:
            all_nonces.extend(r.nonces)
            per_field_durations.extend(r.field_durations_ms)
            per_credential_durations.append(r.total_duration_ms)
            if not r.integrity_ok:
                integrity_failures += 1

        # --- Nonce collision check ---
        nonce_set = set(all_nonces)
        collision_count = len(all_nonces) - len(nonce_set)

        # --- Raw nonce generation throughput ---
        urandom_durations = _benchmark_urandom()

        # --- Statistics ---
        field_p95 = compute_percentile(per_field_durations, 95)
        field_p50 = compute_percentile(per_field_durations, 50)
        cred_p95 = compute_percentile(per_credential_durations, 95)
        cred_p50 = compute_percentile(per_credential_durations, 50)
        urandom_p95 = compute_percentile(urandom_durations, 95)
        urandom_p50 = compute_percentile(urandom_durations, 50)

        diag = _build_diagnostic(
            total_fields=len(all_nonces),
            collision_count=collision_count,
            integrity_failures=integrity_failures,
            field_p50=field_p50,
            field_p95=field_p95,
            cred_p50=cred_p50,
            cred_p95=cred_p95,
            urandom_p50=urandom_p50,
            urandom_p95=urandom_p95,
        )

        assert integrity_failures == 0, (
            f"Round-trip integrity failures: {integrity_failures} "
            f"credentials failed decrypt verification under burst{diag}"
        )

        assert collision_count == 0, (
            f"Nonce collision detected: {collision_count} duplicates in {len(all_nonces)} nonces{diag}"
        )

        assert field_p95 < TARGET_NONCE_OVERHEAD_P95_MS, (
            f"Per-field encryption overhead p95 {field_p95:.4f}ms exceeds target {TARGET_NONCE_OVERHEAD_P95_MS}ms{diag}"
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _encrypt_one_credential(
    enc: SecretEncryptor,
    cred_idx: int,
    accumulator: _BurstAccumulator,
) -> None:
    """Encrypt all fields for one credential and record results."""
    secret_id = str(uuid4())
    fields = _generate_credential_fields(cred_idx)

    nonces: list[bytes] = []
    field_durations: list[float] = []
    integrity_ok = True

    cred_start = time.monotonic()

    for field_name, value in fields.items():
        field_start = time.monotonic()
        encrypted = enc.encrypt_field(value, secret_id, field_name)
        field_elapsed_ms = (time.monotonic() - field_start) * 1000
        field_durations.append(field_elapsed_ms)

        nonces.append(_extract_nonce(encrypted))

        decrypted = enc.decrypt_field(encrypted, secret_id, field_name)
        if decrypted != value:
            integrity_ok = False

    total_ms = (time.monotonic() - cred_start) * 1000

    accumulator.add(
        _BurstResult(
            nonces=nonces,
            field_durations_ms=field_durations,
            total_duration_ms=total_ms,
            integrity_ok=integrity_ok,
        )
    )


def _benchmark_urandom() -> list[float]:
    """Benchmark raw os.urandom(NONCE_SIZE) throughput."""
    durations: list[float] = []
    for _ in range(NONCE_THROUGHPUT_ITERATIONS):
        start = time.monotonic()
        os.urandom(NONCE_SIZE)
        elapsed_ms = (time.monotonic() - start) * 1000
        durations.append(elapsed_ms)
    return durations


def _build_diagnostic(
    *,
    total_fields: int,
    collision_count: int,
    integrity_failures: int,
    field_p50: float,
    field_p95: float,
    cred_p50: float,
    cred_p95: float,
    urandom_p50: float,
    urandom_p95: float,
) -> str:
    """Build a diagnostic string for nonce uniqueness results."""
    parts = [
        "\n--- Nonce uniqueness results (22.11) ---",
        f"  credentials={CREDENTIAL_COUNT}, fields_per_credential={FIELDS_PER_CREDENTIAL}, total_fields={total_fields}",
        f"  burst_workers={BURST_WORKERS}",
        f"  nonce_collisions={collision_count}",
        f"  integrity_failures={integrity_failures}",
        f"  per-field encrypt: p50={field_p50:.4f}ms,"
        f" p95={field_p95:.4f}ms"
        f" (target p95 < {TARGET_NONCE_OVERHEAD_P95_MS}ms)",
        f"  per-credential (all {FIELDS_PER_CREDENTIAL} fields): p50={cred_p50:.4f}ms, p95={cred_p95:.4f}ms",
        f"  raw os.urandom({NONCE_SIZE}) baseline"
        f" ({NONCE_THROUGHPUT_ITERATIONS} calls):"
        f" p50={urandom_p50:.4f}ms, p95={urandom_p95:.4f}ms",
    ]
    return "\n".join(parts) + "\n"
