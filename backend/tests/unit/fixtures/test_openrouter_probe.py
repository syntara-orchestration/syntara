"""Unit tests for the OpenRouter key/model preflight probe."""

from __future__ import annotations

import ssl
from pathlib import Path

import httpx
import pytest
from orchestrator_test_sdk.e2e.openrouter import (
    OPENROUTER_KEY_URL,
    OPENROUTER_MODELS_URL,
    OpenRouterProbeResult,
    OpenRouterStatus,
    apply_openrouter_probe,
    openrouter_ssl_context,
    probe_openrouter,
    probe_openrouter_key,
    probe_openrouter_model,
)


def _client_for(handler: httpx.MockTransport) -> httpx.Client:
    return httpx.Client(transport=handler)


def _router(routes: dict[str, httpx.Response]) -> httpx.MockTransport:
    def _handle(request: httpx.Request) -> httpx.Response:
        response = routes.get(str(request.url))
        assert response is not None, f"unexpected URL {request.url}"
        return response

    return httpx.MockTransport(_handle)


def test_probe_key_ok_with_remaining_credits() -> None:
    transport = _router(
        {OPENROUTER_KEY_URL: httpx.Response(200, json={"data": {"limit_remaining": 8.5}})},
    )
    with _client_for(transport) as client:
        result = probe_openrouter_key("sk-test", client=client)
    assert result.status is OpenRouterStatus.OK


def test_probe_key_invalid() -> None:
    transport = _router({OPENROUTER_KEY_URL: httpx.Response(401, json={"error": "unauthorized"})})
    with _client_for(transport) as client:
        result = probe_openrouter_key("sk-bad", client=client)
    assert result.status is OpenRouterStatus.INVALID_KEY


def test_probe_key_no_credits() -> None:
    transport = _router(
        {OPENROUTER_KEY_URL: httpx.Response(200, json={"data": {"limit_remaining": 0}})},
    )
    with _client_for(transport) as client:
        result = probe_openrouter_key("sk-test", client=client)
    assert result.status is OpenRouterStatus.NO_CREDITS


def test_probe_model_in_catalog() -> None:
    transport = _router(
        {
            OPENROUTER_MODELS_URL: httpx.Response(
                200, json={"data": [{"id": "anthropic/claude-sonnet-4.5"}, {"id": "moonshotai/kimi-k2"}]}
            )
        },
    )
    with _client_for(transport) as client:
        result = probe_openrouter_model("sk-test", "anthropic/claude-sonnet-4.5", client=client)
    assert result.status is OpenRouterStatus.OK


def test_probe_model_missing_from_catalog() -> None:
    transport = _router(
        {OPENROUTER_MODELS_URL: httpx.Response(200, json={"data": [{"id": "moonshotai/kimi-k2"}]})},
    )
    with _client_for(transport) as client:
        result = probe_openrouter_model("sk-test", "anthropic/claude-sonnet-4.5", client=client)
    assert result.status is OpenRouterStatus.UNKNOWN_MODEL
    assert "anthropic/claude-sonnet-4.5" in result.detail


def test_probe_openrouter_checks_key_then_model() -> None:
    transport = _router(
        {
            OPENROUTER_KEY_URL: httpx.Response(200, json={"data": {"limit_remaining": 1.0}}),
            OPENROUTER_MODELS_URL: httpx.Response(200, json={"data": [{"id": "moonshotai/kimi-k2"}]}),
        },
    )
    with _client_for(transport) as client:
        result = probe_openrouter("sk-test", "moonshotai/kimi-k2", client=client)
    assert result.status is OpenRouterStatus.OK


def test_probe_openrouter_stops_on_invalid_key() -> None:
    transport = _router({OPENROUTER_KEY_URL: httpx.Response(401, json={"error": "unauthorized"})})
    with _client_for(transport) as client:
        result = probe_openrouter("sk-bad", "anthropic/claude-sonnet-4.5", client=client)
    assert result.status is OpenRouterStatus.INVALID_KEY


def test_apply_probe_xfails_on_no_credits() -> None:
    with pytest.raises(pytest.xfail.Exception, match="insufficient credits"):
        apply_openrouter_probe(OpenRouterProbeResult(OpenRouterStatus.NO_CREDITS, "OpenRouter insufficient credits"))


def test_apply_probe_skips_on_unknown_model() -> None:
    with pytest.raises(pytest.skip.Exception, match="not in the catalog"):
        apply_openrouter_probe(
            OpenRouterProbeResult(OpenRouterStatus.UNKNOWN_MODEL, "OpenRouter model 'x' is not in the catalog")
        )


def test_openrouter_ssl_context_keeps_distro_cas_when_ssl_cert_file_is_narrow(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    openssl_cafile = ssl.get_default_verify_paths().openssl_cafile
    bundle_path = next(
        (
            Path(raw)
            for raw in (
                openssl_cafile,
                "/etc/pki/tls/certs/ca-bundle.crt",
                "/etc/pki/tls/cert.pem",
                "/etc/ssl/certs/ca-certificates.crt",
            )
            if raw and Path(raw).is_file()
        ),
        None,
    )
    if bundle_path is None:
        pytest.skip("no OS CA bundle present")
    bundle = bundle_path.read_text()
    begin, end_marker = "-----BEGIN CERTIFICATE-----", "-----END CERTIFICATE-----"
    start, end = bundle.find(begin), bundle.find(end_marker)
    if start < 0 or end < 0:
        pytest.skip("OS CA bundle has no PEM certificates")
    ca_path = tmp_path / "cluster-ca.pem"
    ca_path.write_text(bundle[start : end + len(end_marker)] + "\n")
    monkeypatch.setenv("SSL_CERT_FILE", str(ca_path))
    openrouter_ssl_context.cache_clear()
    try:
        narrow = ssl.create_default_context(cafile=str(ca_path))
        ctx = openrouter_ssl_context()
        assert ctx.verify_mode == ssl.CERT_REQUIRED
        assert len(ctx.get_ca_certs()) > len(narrow.get_ca_certs())
    finally:
        openrouter_ssl_context.cache_clear()


def test_probe_uses_openrouter_ssl_context(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_get(url: str, **kwargs: object) -> httpx.Response:
        captured["url"] = url
        captured.update(kwargs)
        return httpx.Response(200, json={"data": {"limit_remaining": 1.0}})

    monkeypatch.setattr(httpx, "get", fake_get)
    result = probe_openrouter_key("sk-test")
    assert result.status is OpenRouterStatus.OK
    assert captured["url"] == OPENROUTER_KEY_URL
    assert captured["verify"] is openrouter_ssl_context()
