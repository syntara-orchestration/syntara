"""Unit tests for E2E httpbin URL selection."""

from __future__ import annotations

import pytest
from orchestrator_test_sdk.e2e.helpers import (
    _IN_CLUSTER_HTTPBIN_URL,
    _PUBLIC_HTTPBIN_URL,
    resolve_httpbin_url,
)


@pytest.mark.parametrize(
    ("configured", "in_kubernetes", "expected"),
    [
        (None, False, _PUBLIC_HTTPBIN_URL),
        (None, True, _IN_CLUSTER_HTTPBIN_URL),
        ("http://httpbin:8080", False, "http://httpbin:8080"),
        ("http://httpbin:8080/", True, "http://httpbin:8080"),
        ("https://httpbin.org", True, "https://httpbin.org"),
        ("https://evil.example.com", True, _IN_CLUSTER_HTTPBIN_URL),
        ("https://evilhttpbin.com", True, _IN_CLUSTER_HTTPBIN_URL),
        ("https://evilhttpbin.com", False, _PUBLIC_HTTPBIN_URL),
        ("http://attacker-httpbin.net", False, _PUBLIC_HTTPBIN_URL),
        ("https://httpbin.org.evil.com", True, _IN_CLUSTER_HTTPBIN_URL),
        ("ftp://httpbin.org", False, _PUBLIC_HTTPBIN_URL),
    ],
)
def test_resolve_httpbin_url(configured: str | None, in_kubernetes: bool, expected: str) -> None:  # noqa: FBT001
    assert resolve_httpbin_url(configured, in_kubernetes=in_kubernetes) == expected


def test_resolve_httpbin_url_reads_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HTTPBIN_URL", "http://httpbin:8080")
    monkeypatch.delenv("KUBERNETES_SERVICE_HOST", raising=False)
    assert resolve_httpbin_url() == "http://httpbin:8080"


def test_resolve_httpbin_url_uses_kubernetes_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HTTPBIN_URL", raising=False)
    monkeypatch.setenv("KUBERNETES_SERVICE_HOST", "10.96.0.1")
    assert resolve_httpbin_url() == _IN_CLUSTER_HTTPBIN_URL
