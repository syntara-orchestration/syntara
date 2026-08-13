"""Suite 22 — Credential Storage: Injector Resolution KPI (22.8).

Test 22.8: InjectorResolver template resolution — resolve 200
    credentials with varying template complexity
    KPI: Injector Resolution Time (p95) < 5ms per credential
    Measurement: Component-level timing
    Validation:
        Time InjectorResolver.resolve() for each credential type's
        injector templates

This test exercises the template resolver directly (no network I/O)
to isolate the regex-based substitution overhead from API latency.

Note: This test validates template substitution logic, not SSH key validity.
Synthetic keys are used to avoid requiring PERF_TEST_SSH_PRIVATE_KEY for
component-level tests. Integration tests use real keys from the environment.

Run with:
    make test-integration-coverage
"""

from __future__ import annotations

import time
from typing import Any
from uuid import uuid4

from syntara.credentials.lib.injector_resolver import InjectorResolver, ResolvedInjectors
from tests.integration.helpers.perf import compute_percentile

RESOLUTIONS_PER_TYPE = 40
TARGET_RESOLUTION_P95_MS = 5

INJECTOR_TEMPLATES: dict[str, dict[str, Any]] = {
    "HTTP Bearer Token": {
        "extra_vars": {"auth_type": "bearer", "bearer_token": "{{token}}"},
        "env": {},
        "file": {},
    },
    "HTTP Basic Auth": {
        "extra_vars": {
            "auth_type": "basic",
            "basic_username": "{{username}}",
            "basic_password": "{{password}}",
        },
        "env": {},
        "file": {},
    },
    "Ansible Automation Platform": {
        "extra_vars": {
            "auth_type": "aap",
            "aap_username": "{{username}}",
            "aap_password": "{{password}}",
            "aap_oauth_token": "{{oauth_token}}",
        },
        "env": {},
        "file": {},
    },
    "LLM Provider": {
        "extra_vars": {
            "auth_type": "api_key",
            "llm_api_key": "{{api_key}}",
        },
        "env": {},
        "file": {},
    },
    "SSH Key": {
        "extra_vars": {
            "auth_type": "ssh",
            "ssh_username": "{{username}}",
            "ssh_private_key": "{{ssh_private_key}}",
        },
        "env": {},
        "file": {},
    },
}

DECRYPTED_INPUTS: dict[str, dict[str, Any]] = {
    "HTTP Bearer Token": {
        "token": f"sk-perf-{uuid4().hex}",
    },
    "HTTP Basic Auth": {
        "username": "perf-user",
        "password": f"perf-pass-{uuid4().hex}",
    },
    "Ansible Automation Platform": {
        "username": "perf-aap-user",
        "password": f"perf-aap-pass-{uuid4().hex}",
        "oauth_token": f"oat-{uuid4().hex}",
    },
    "LLM Provider": {
        "api_key": f"sk-llm-{uuid4().hex}",
    },
    "SSH Key": {
        "username": "perf-ssh-user",
        # Synthetic key: only template substitution is tested, not SSH key validity
        "ssh_private_key": (
            "-----BEGIN OPENSSH PRIVATE KEY-----\n" + uuid4().hex * 4 + "\n-----END OPENSSH PRIVATE KEY-----"
        ),
    },
}

COMPLEX_INJECTOR: dict[str, Any] = {
    "extra_vars": {
        "auth_type": "complex",
        "url": "https://{{host}}:{{port}}/{{path}}",
        "full_auth": "{{username}}:{{password}}@{{host}}",
        "field_0": "{{field_0}}",
        "field_1": "{{field_1}}",
        "field_2": "{{field_2}}",
        "field_3": "{{field_3}}",
        "field_4": "{{field_4}}",
    },
    "env": {
        "SERVICE_URL": "https://{{host}}:{{port}}",
        "SERVICE_TOKEN": "{{token}}",
        "SERVICE_KEY": "{{api_key}}",
    },
    "file": {
        "parameters": "host={{host}}\nport={{port}}\nuser={{username}}\npass={{password}}",
        "key_file": "{{ssh_private_key}}",
    },
}

COMPLEX_INPUTS: dict[str, Any] = {
    "host": "complex.perf-test.example.com",
    "port": "8443",
    "path": "api/v2/resource",
    "username": "complex-user",
    "password": f"complex-pass-{uuid4().hex}",
    "token": f"tok-{uuid4().hex}",
    "api_key": f"key-{uuid4().hex}",
    # Synthetic key: only template substitution is tested, not SSH key validity
    "ssh_private_key": "-----BEGIN OPENSSH PRIVATE KEY-----\n" + uuid4().hex * 4,
    "field_0": f"value-{uuid4().hex}",
    "field_1": f"value-{uuid4().hex}",
    "field_2": f"value-{uuid4().hex}",
    "field_3": f"value-{uuid4().hex}",
    "field_4": f"value-{uuid4().hex}",
}

TYPE_NAMES = list(INJECTOR_TEMPLATES.keys())


class TestInjectorResolution:
    """22.8 — InjectorResolver.resolve() template resolution.

    Calls InjectorResolver.resolve() 200 times across all 5 managed
    credential types (40 per type), plus an additional complex template
    with multiple sections and inline concatenated templates.

    Validates:
        - p95 resolution time < 5ms per credential for each type
        - Overall p95 across all types < 5ms
        - Resolved output values are correct (templates fully substituted)
    """

    def test_injector_resolution_p95(self) -> None:
        """Resolve 200+ injector templates; p95 must be < 5ms."""
        all_durations: list[float] = []
        per_type_results: dict[str, dict[str, float]] = {}

        for type_name in TYPE_NAMES:
            durations = _bench_type(type_name)
            p95 = compute_percentile(durations, 95)
            p50 = compute_percentile(durations, 50)
            per_type_results[type_name] = {"p50": p50, "p95": p95}
            all_durations.extend(durations)

        complex_durations = _bench_complex()
        complex_p95 = compute_percentile(complex_durations, 95)
        complex_p50 = compute_percentile(complex_durations, 50)
        per_type_results["(complex template)"] = {"p50": complex_p50, "p95": complex_p95}
        all_durations.extend(complex_durations)

        overall_p95 = compute_percentile(all_durations, 95)
        overall_p50 = compute_percentile(all_durations, 50)

        diag_parts = [
            "\n--- Injector resolution results (22.8) ---",
            f"  resolutions_per_type={RESOLUTIONS_PER_TYPE}",
            f"  total_resolutions={len(all_durations)}",
            f"  overall: p50={overall_p50:.3f}ms, p95={overall_p95:.3f}ms",
        ]
        failures: list[str] = []
        for name, stats in per_type_results.items():
            template_count = len(INJECTOR_TEMPLATES.get(name, COMPLEX_INJECTOR).get("extra_vars", {}))
            diag_parts.append(f"  {name} ({template_count} vars): p50={stats['p50']:.3f}ms, p95={stats['p95']:.3f}ms")
            if stats["p95"] >= TARGET_RESOLUTION_P95_MS:
                failures.append(f"{name}: p95={stats['p95']:.3f}ms")
        diag = "\n".join(diag_parts) + "\n"

        assert not failures, (
            f"Injector resolution p95 exceeded {TARGET_RESOLUTION_P95_MS}ms for: {'; '.join(failures)}{diag}"
        )
        assert overall_p95 < TARGET_RESOLUTION_P95_MS, (
            f"Overall injector resolution p95 {overall_p95:.3f}ms exceeds target {TARGET_RESOLUTION_P95_MS}ms{diag}"
        )


# ---------------------------------------------------------------------------
# Benchmarking helpers
# ---------------------------------------------------------------------------


def _bench_type(type_name: str) -> list[float]:
    """Benchmark InjectorResolver.resolve() for a single credential type."""
    injectors = INJECTOR_TEMPLATES[type_name]
    base_inputs = DECRYPTED_INPUTS[type_name]
    durations: list[float] = []

    for _ in range(RESOLUTIONS_PER_TYPE):
        inputs = dict(base_inputs)

        start = time.monotonic()
        result = InjectorResolver.resolve(injectors, inputs)
        elapsed_ms = (time.monotonic() - start) * 1000

        assert isinstance(result, ResolvedInjectors)
        _verify_no_unresolved_templates(result)
        durations.append(elapsed_ms)

    return durations


def _bench_complex() -> list[float]:
    """Benchmark InjectorResolver.resolve() for a complex multi-section template."""
    durations: list[float] = []

    for _ in range(RESOLUTIONS_PER_TYPE):
        start = time.monotonic()
        result = InjectorResolver.resolve(COMPLEX_INJECTOR, COMPLEX_INPUTS)
        elapsed_ms = (time.monotonic() - start) * 1000

        assert isinstance(result, ResolvedInjectors)
        _verify_no_unresolved_templates(result)

        assert COMPLEX_INPUTS["host"] in result.extra_vars["url"]
        assert COMPLEX_INPUTS["username"] in result.extra_vars["full_auth"]
        assert result.env["SERVICE_TOKEN"] == COMPLEX_INPUTS["token"]
        assert COMPLEX_INPUTS["host"] in result.file["parameters"]

        durations.append(elapsed_ms)

    return durations


def _verify_no_unresolved_templates(resolved: ResolvedInjectors) -> None:
    """Assert that no {{field_id}} placeholders remain in the resolved output."""
    import re

    pattern = re.compile(r"\{\{\w+\}\}")
    for section_name in ("extra_vars", "env", "file"):
        section = getattr(resolved, section_name)
        for key, value in section.items():
            if isinstance(value, str):
                assert not pattern.search(value), f"Unresolved template in {section_name}.{key}: {value!r}"
