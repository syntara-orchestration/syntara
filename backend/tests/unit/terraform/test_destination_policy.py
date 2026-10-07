"""Destination policy tests for TFE.

Covers loopback, cloud metadata, link-local, private addresses, redirects to disallowed targets,
and approved self-managed destinations for TFE paths.
"""

from __future__ import annotations

from unittest.mock import patch

import httpx
import pytest
import respx

from syntara.integrations.lib.url_validation import validate_integration_configuration_no_ssrf
from syntara.integrations.models.integration_configuration import TFEConfiguration
from syntara.terraform.client import TFEClient
from syntara.terraform.errors import TFEError, TFEErrorCode

BASE_URL = "https://terraform.example.com/api/v2"
_PUBLIC_IP = "93.184.216.34"
_PATCH_GETADDRINFO = "socket.getaddrinfo"
_PATCH_CLIENT_SETTINGS = "syntara.terraform.client.get_settings"
_PATCH_INTEGRATION_SETTINGS = "syntara.integrations.lib.url_validation.get_settings"


def _mock_getaddrinfo(ip: str) -> list[tuple[None, None, None, None, tuple[str, int]]]:
    return [(None, None, None, None, (ip, 0))]


def _settings(allowed: list[str]) -> object:
    return type("S", (), {"integration_url_allowed_hosts": allowed})()


@pytest.fixture
def client() -> TFEClient:
    return TFEClient(base_url="https://terraform.example.com", token="test", organization="acme")  # noqa: S106


def _tfe_config(base_url: str, *, allow_http: bool = False) -> TFEConfiguration:
    return TFEConfiguration(
        base_url=base_url,
        organization="acme",
        allow_http=allow_http,
    )


# ── Integration base_url (shared choke point) ───────────────────────────────


class TestTFEConfigurationDestinationPolicy:
    """TFE integration base_url uses shared integration SSRF policy (AC5)."""

    @pytest.mark.ssrf_enforced
    def test_loopback_rejected(self) -> None:
        config = _tfe_config("http://127.0.0.1", allow_http=True)
        with pytest.raises(ValueError, match="SSRF blocked"):
            validate_integration_configuration_no_ssrf(config)

    @pytest.mark.ssrf_enforced
    def test_cloud_metadata_rejected(self) -> None:
        config = _tfe_config("https://169.254.169.254")
        with pytest.raises(ValueError, match="SSRF blocked"):
            validate_integration_configuration_no_ssrf(config)

    @pytest.mark.ssrf_enforced
    def test_link_local_rejected(self) -> None:
        config = _tfe_config("https://169.254.1.1")
        with pytest.raises(ValueError, match="SSRF blocked"):
            validate_integration_configuration_no_ssrf(config)

    @pytest.mark.ssrf_enforced
    def test_private_address_rejected(self) -> None:
        config = _tfe_config("https://10.0.0.25")
        with pytest.raises(ValueError, match="SSRF blocked"):
            validate_integration_configuration_no_ssrf(config)

    @pytest.mark.ssrf_enforced
    def test_approved_self_managed_destination_accepted(self) -> None:
        """Allowlisted self-managed TFE host may resolve to a private address."""
        with (
            patch(_PATCH_GETADDRINFO, return_value=_mock_getaddrinfo("10.0.0.25")),
            patch(_PATCH_INTEGRATION_SETTINGS, return_value=_settings(["tfe.internal.corp"])),
        ):
            validate_integration_configuration_no_ssrf(_tfe_config("https://tfe.internal.corp"))

    @pytest.mark.ssrf_enforced
    def test_allowlist_does_not_permit_cloud_metadata(self) -> None:
        config = _tfe_config("https://169.254.169.254")
        with (
            patch(_PATCH_INTEGRATION_SETTINGS, return_value=_settings(["169.254.169.254"])),
            pytest.raises(ValueError, match="SSRF blocked"),
        ):
            validate_integration_configuration_no_ssrf(config)


# ── Upload URL (execution-time destination check) ───────────────────────────


class TestTFEUploadDestinationPolicy:
    """upload_configuration_version validates destinations before credentials leave AO."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "upload_url",
        [
            "http://127.0.0.1/upload",
            "http://169.254.169.254/latest/meta-data/",
            "http://169.254.1.1/upload",
            "http://10.0.0.25/upload",
            "http://192.168.1.50/upload",
        ],
    )
    async def test_restricted_upload_destinations_rejected(self, client: TFEClient, upload_url: str) -> None:
        with pytest.raises(TFEError) as exc_info:
            await client.upload_configuration_version(upload_url, b"archive")
        assert exc_info.value.error_code == TFEErrorCode.VALIDATION
        assert "outbound URL policy" in exc_info.value.message
        assert exc_info.value.retryable is False

    @pytest.mark.asyncio
    @respx.mock
    async def test_approved_self_managed_upload_destination_accepted(self, client: TFEClient) -> None:
        upload_url = "https://uploads.tfe.internal.corp/config"
        route = respx.put(upload_url).mock(return_value=httpx.Response(200))
        with (
            patch(_PATCH_GETADDRINFO, return_value=_mock_getaddrinfo("10.0.0.25")),
            patch(_PATCH_CLIENT_SETTINGS, return_value=_settings(["uploads.tfe.internal.corp"])),
        ):
            await client.upload_configuration_version(upload_url, b"archive")
        assert route.called
        assert "Authorization" not in route.calls[0].request.headers

    @pytest.mark.asyncio
    @respx.mock
    async def test_public_upload_destination_accepted(self, client: TFEClient) -> None:
        upload_url = "https://uploads.example.com/config"
        route = respx.put(upload_url).mock(return_value=httpx.Response(204))
        with (
            patch(_PATCH_GETADDRINFO, return_value=_mock_getaddrinfo(_PUBLIC_IP)),
            patch(_PATCH_CLIENT_SETTINGS, return_value=_settings([])),
        ):
            await client.upload_configuration_version(upload_url, b"archive")
        assert route.called


# ── Redirects ───────────────────────────────────────────────────────────────


class TestTFERedirectDestinationPolicy:
    """TFE HTTP client must not follow redirects to disallowed destinations (AC5)."""

    @pytest.mark.asyncio
    @respx.mock
    async def test_api_redirect_to_metadata_is_not_followed(self, client: TFEClient) -> None:
        disallowed = "https://169.254.169.254/latest/meta-data/"
        api = respx.get(f"{BASE_URL}/runs/run-1").mock(
            return_value=httpx.Response(302, headers={"Location": disallowed})
        )
        metadata = respx.get(disallowed).mock(return_value=httpx.Response(200, text="ami-id"))

        with pytest.raises(TFEError):
            await client.get_run("run-1")

        assert api.called
        assert not metadata.called
        # Credential stayed on the original request only.
        assert "Authorization" in api.calls[0].request.headers

    @pytest.mark.asyncio
    @respx.mock
    async def test_upload_redirect_to_private_address_is_not_followed(self, client: TFEClient) -> None:
        upload_url = "https://uploads.example.com/config"
        private = "https://10.0.0.25/stolen"
        upload = respx.put(upload_url).mock(return_value=httpx.Response(302, headers={"Location": private}))
        private_route = respx.put(private).mock(return_value=httpx.Response(200))

        with (
            patch(_PATCH_GETADDRINFO, return_value=_mock_getaddrinfo(_PUBLIC_IP)),
            patch(_PATCH_CLIENT_SETTINGS, return_value=_settings([])),
            pytest.raises(TFEError),
        ):
            await client.upload_configuration_version(upload_url, b"archive")

        assert upload.called
        assert not private_route.called
