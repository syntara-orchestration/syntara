"""Lightweight OpenRouter probes for E2E LLM fixtures.

Validates ``APP_OPENROUTER_API_KEY`` and ``APP_OPENROUTER_MODEL`` with two cheap
GETs (``/api/v1/key`` and ``/api/v1/models``) so agentic tests skip or xfail
before starting a 180s workflow poll.
"""

from __future__ import annotations

import ssl
from dataclasses import dataclass
from enum import StrEnum
from functools import lru_cache
from pathlib import Path

import httpx
import pytest

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
OPENROUTER_KEY_URL = f"{OPENROUTER_BASE_URL}/key"
OPENROUTER_MODELS_URL = f"{OPENROUTER_BASE_URL}/models"
DEFAULT_OPENROUTER_MODEL = "anthropic/claude-sonnet-4.5"
_TIMEOUT = 10.0


class OpenRouterStatus(StrEnum):
    """Outcome of an OpenRouter key/model probe."""

    OK = "ok"
    INVALID_KEY = "invalid_key"
    NO_CREDITS = "no_credits"
    UNKNOWN_MODEL = "unknown_model"
    UNREACHABLE = "unreachable"


@dataclass(frozen=True, slots=True)
class OpenRouterProbeResult:
    """Result of probing OpenRouter for key validity, credits, and model id."""

    status: OpenRouterStatus
    detail: str

    @property
    def ok(self) -> bool:
        return self.status is OpenRouterStatus.OK


# Distro bundles used when ``SSL_CERT_FILE`` has replaced the public store with a
# cluster/S2S CA. openssl_cafile is first; the rest cover RHEL/UBI and Debian.
_DISTRO_CA_FILES = (
    "/etc/pki/tls/certs/ca-bundle.crt",
    "/etc/pki/tls/cert.pem",
    "/etc/ssl/certs/ca-certificates.crt",
)


def _distro_ca_files() -> tuple[Path, ...]:
    """OS CA bundles, resolved and de-duplicated, independent of ``SSL_CERT_FILE``."""
    candidates = [ssl.get_default_verify_paths().openssl_cafile, *_DISTRO_CA_FILES]
    files: list[Path] = []
    seen: set[Path] = set()
    for raw in candidates:
        if not raw:
            continue
        try:
            path = Path(raw).resolve()
        except OSError:
            continue
        if path in seen or not path.is_file():
            continue
        seen.add(path)
        files.append(path)
    return tuple(files)


@lru_cache(maxsize=1)
def openrouter_ssl_context() -> ssl.SSLContext:
    """Trust public distro CAs plus whatever ``SSL_CERT_FILE`` already provides.

    Konflux pytest runs in ``ubi9/python-312`` with ``SSL_CERT_FILE`` often pointed
    at the Kind/S2S CA only (see ``nexus-tests-env-variables``). ``httpx`` then
    verifies against that file alone and rejects OpenRouter's Google Trust
    Services chain. Reloading the OS bundle restores public roots without
    dropping a cluster proxy CA that ``create_default_context`` already picked up.
    """
    ctx = ssl.create_default_context()
    for cafile in _distro_ca_files():
        ctx.load_verify_locations(cafile=str(cafile))
    capath = ssl.get_default_verify_paths().openssl_capath
    if capath and Path(capath).is_dir():
        ctx.load_verify_locations(capath=capath)
    return ctx


def _get(url: str, *, headers: dict[str, str], client: httpx.Client | None) -> httpx.Response:
    if client is not None:
        return client.get(url, headers=headers)
    return httpx.get(url, headers=headers, timeout=_TIMEOUT, verify=openrouter_ssl_context())


def parse_limit_remaining(response: httpx.Response) -> float | None:
    """Parse remaining credits from a ``GET /api/v1/key`` response.

    ``None`` means the balance is unknown (do not treat as exhausted). HTTP 402
    is treated as a remaining balance of 0.
    """
    if response.status_code == 402:
        return 0.0
    if response.status_code != 200:
        return None
    try:
        remaining = response.json().get("data", {}).get("limit_remaining")
        return None if remaining is None else float(remaining)
    except (TypeError, ValueError):
        return None


def probe_openrouter_key(api_key: str, *, client: httpx.Client | None = None) -> OpenRouterProbeResult:
    """Check that *api_key* is accepted and has remaining credits."""
    headers = {"Authorization": f"Bearer {api_key}"}
    try:
        response = _get(OPENROUTER_KEY_URL, headers=headers, client=client)
    except httpx.HTTPError as exc:
        return OpenRouterProbeResult(OpenRouterStatus.UNREACHABLE, f"OpenRouter key probe failed: {exc}")

    if response.status_code in {401, 403}:
        return OpenRouterProbeResult(OpenRouterStatus.INVALID_KEY, "OpenRouter API key is invalid")
    if response.status_code == 402:
        return OpenRouterProbeResult(OpenRouterStatus.NO_CREDITS, "OpenRouter insufficient credits")
    if response.status_code != 200:
        return OpenRouterProbeResult(
            OpenRouterStatus.UNREACHABLE,
            f"OpenRouter key probe returned HTTP {response.status_code}",
        )

    remaining = parse_limit_remaining(response)
    if remaining is not None and remaining <= 0:
        return OpenRouterProbeResult(OpenRouterStatus.NO_CREDITS, "OpenRouter insufficient credits")
    return OpenRouterProbeResult(OpenRouterStatus.OK, "OpenRouter API key is valid")


def probe_openrouter_model(api_key: str, model: str, *, client: httpx.Client | None = None) -> OpenRouterProbeResult:
    """Check that *model* is present in the OpenRouter catalog."""
    headers = {"Authorization": f"Bearer {api_key}"}
    try:
        response = _get(OPENROUTER_MODELS_URL, headers=headers, client=client)
    except httpx.HTTPError as exc:
        return OpenRouterProbeResult(OpenRouterStatus.UNREACHABLE, f"OpenRouter models probe failed: {exc}")

    if response.status_code in {401, 403}:
        return OpenRouterProbeResult(OpenRouterStatus.INVALID_KEY, "OpenRouter API key is invalid")
    if response.status_code != 200:
        return OpenRouterProbeResult(
            OpenRouterStatus.UNREACHABLE,
            f"OpenRouter models probe returned HTTP {response.status_code}",
        )

    try:
        payload = response.json().get("data", [])
    except ValueError:
        return OpenRouterProbeResult(OpenRouterStatus.UNREACHABLE, "OpenRouter models probe returned invalid JSON")

    model_ids = {item.get("id") for item in payload if isinstance(item, dict)}
    if model not in model_ids:
        return OpenRouterProbeResult(
            OpenRouterStatus.UNKNOWN_MODEL,
            f"OpenRouter model {model!r} is not in the catalog",
        )
    return OpenRouterProbeResult(OpenRouterStatus.OK, f"OpenRouter model {model!r} is available")


def probe_openrouter(api_key: str, model: str, *, client: httpx.Client | None = None) -> OpenRouterProbeResult:
    """Validate the API key (and credits) then that *model* exists in the catalog."""
    key_result = probe_openrouter_key(api_key, client=client)
    if key_result.status is not OpenRouterStatus.OK:
        return key_result
    return probe_openrouter_model(api_key, model, client=client)


def apply_openrouter_probe(result: OpenRouterProbeResult) -> None:
    """Xfail on empty credits; skip on any other probe failure; no-op when OK."""
    if result.status is OpenRouterStatus.OK:
        return
    if result.status is OpenRouterStatus.NO_CREDITS:
        pytest.xfail(result.detail)
    pytest.skip(result.detail)
