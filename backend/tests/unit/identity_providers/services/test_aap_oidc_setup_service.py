"""Tests for AAPOIDCSetupService."""

from collections.abc import Callable
from contextlib import AbstractContextManager
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import respx
from pydantic import HttpUrl

from syntara.core.config.base import get_settings
from syntara.identity_providers.exceptions import (
    AAPAuthenticationError,
    AAPConnectionError,
    AAPSetupError,
)
from syntara.identity_providers.models.aap_setup import AAPOIDCSetupRequest
from syntara.identity_providers.models.identity_provider_configuration import OIDCIdpType
from syntara.identity_providers.services.aap_oidc_setup_service import AAPOIDCSetupService

_AAP_URL = "https://aap.example.com"
_AAP_API = f"{_AAP_URL}/api/gateway/v1"
_TEST_PRODUCT_NAME = "TestProduct"


@pytest.fixture(autouse=True)
def _aap_settings(override_settings: Callable[..., AbstractContextManager[object]]) -> object:
    with override_settings(
        server_public_url=HttpUrl("https://example.com"),
        cors_allow_origins=["https://example.com"],
        product_name=_TEST_PRODUCT_NAME,
    ):
        yield


def _mock_settings() -> MagicMock:
    settings = MagicMock()
    settings.jwt_issuer = "https://example.com"
    settings.post_logout_redirect_uri = "https://example.com"
    settings.cors_allow_origins = ["https://example.com"]
    settings.product_name = _TEST_PRODUCT_NAME
    return settings


def _mock_idp_service() -> MagicMock:
    service = MagicMock()
    service.create_provider = AsyncMock(
        return_value=MagicMock(
            id="test-id",
            name="Ansible Automation Platform",
            configuration=MagicMock(idp_type=OIDCIdpType.AAP),
        )
    )
    return service


def _make_request(
    aap_url: str = _AAP_URL,
    organization: str = "Default",
    admin_username: str | None = "admin",
    admin_password: str | None = "secret",  # noqa: S107 -- test fixture
    personal_access_token: str | None = None,
    *,
    insecure_skip_tls_verify: bool = False,
) -> AAPOIDCSetupRequest:
    return AAPOIDCSetupRequest(
        aap_url=aap_url,
        organization=organization,
        admin_username=admin_username,
        admin_password=admin_password,
        personal_access_token=personal_access_token,
        insecure_skip_tls_verify=insecure_skip_tls_verify,
    )


def _make_pat_request(
    aap_url: str = _AAP_URL,
    organization: str = "Default",
    personal_access_token: str = "my-pat-token",  # noqa: S107 -- test fixture
    *,
    insecure_skip_tls_verify: bool = False,
) -> AAPOIDCSetupRequest:
    return AAPOIDCSetupRequest(
        aap_url=aap_url,
        organization=organization,
        personal_access_token=personal_access_token,
        insecure_skip_tls_verify=insecure_skip_tls_verify,
    )


def _make_service(
    idp_service: MagicMock | None = None,
) -> AAPOIDCSetupService:
    return AAPOIDCSetupService(
        idp_service=idp_service or _mock_idp_service(),
        settings=get_settings(),
    )


def _org_response(org_id: int = 1, name: str = "Default") -> dict[str, object]:
    return {"count": 1, "results": [{"id": org_id, "name": name}]}


def _app_response(
    client_id: str = "test-client-id",
    client_secret: str = "test-client-secret",  # noqa: S107 -- test fixture
) -> dict[str, object]:
    return {
        "id": 1,
        "name": _TEST_PRODUCT_NAME,
        "client_id": client_id,
        "client_secret": client_secret,
        "client_type": "confidential",
        "authorization_grant_type": "authorization-code",
    }


class TestSetupHappyPath:
    """Tests for successful AAP OIDC setup."""

    @pytest.mark.asyncio
    @respx.mock
    async def test_creates_idp_with_aap_presets(self) -> None:
        respx.get(f"{_AAP_API}/organizations/").mock(return_value=httpx.Response(200, json=_org_response()))
        respx.post(f"{_AAP_API}/applications/").mock(return_value=httpx.Response(201, json=_app_response()))

        idp_service = _mock_idp_service()
        service = _make_service(idp_service=idp_service)
        await service.setup(_make_request())

        idp_service.create_provider.assert_awaited_once()
        create_arg = idp_service.create_provider.call_args[0][0]

        assert create_arg.name == "Ansible Automation Platform"
        config = create_arg.configuration
        assert config.idp_type == OIDCIdpType.AAP
        assert config.client_id == "test-client-id"
        assert config.client_secret == "test-client-secret"  # noqa: S105 -- test assertion
        assert str(config.issuer_url) == f"{_AAP_URL}/o/"
        assert config.scopes == "read write openid roles"
        assert config.aap_role_mapping_enabled is True
        assert config.enable_rp_initiated_logout is True
        assert config.auto_discovery is True
        assert config.allow_all_authenticated is False

    @pytest.mark.asyncio
    @respx.mock
    async def test_constructs_redirect_uri_from_settings(self) -> None:
        respx.get(f"{_AAP_API}/organizations/").mock(return_value=httpx.Response(200, json=_org_response()))
        respx.post(f"{_AAP_API}/applications/").mock(return_value=httpx.Response(201, json=_app_response()))

        idp_service = _mock_idp_service()
        service = _make_service(idp_service=idp_service)
        await service.setup(_make_request())

        create_arg = idp_service.create_provider.call_args[0][0]
        assert str(create_arg.configuration.redirect_uri) == "https://example.com/api/v1/auth/oidc/callback"

    @pytest.mark.asyncio
    @respx.mock
    async def test_passes_organization_id_to_app_creation(self) -> None:
        import json

        respx.get(f"{_AAP_API}/organizations/").mock(return_value=httpx.Response(200, json=_org_response(org_id=42)))
        app_route = respx.post(f"{_AAP_API}/applications/").mock(return_value=httpx.Response(201, json=_app_response()))

        service = _make_service()
        await service.setup(_make_request())

        body = json.loads(app_route.calls[0].request.content.decode())
        assert body["organization"] == 42

    @pytest.mark.asyncio
    @respx.mock
    async def test_tls_skip_propagated(self) -> None:
        respx.get(f"{_AAP_API}/organizations/").mock(return_value=httpx.Response(200, json=_org_response()))
        respx.post(f"{_AAP_API}/applications/").mock(return_value=httpx.Response(201, json=_app_response()))

        idp_service = _mock_idp_service()
        service = _make_service(idp_service=idp_service)
        await service.setup(_make_request(insecure_skip_tls_verify=True))

        config = idp_service.create_provider.call_args[0][0].configuration
        assert config.disable_tls_verify is True

    @pytest.mark.asyncio
    async def test_tls_skip_passes_verify_false_to_httpx_client(self) -> None:
        mock_client = AsyncMock()
        mock_client.request.side_effect = [
            MagicMock(status_code=200, json=MagicMock(return_value=_org_response())),
            MagicMock(status_code=201, json=MagicMock(return_value=_app_response())),
        ]

        with patch("syntara.identity_providers.services.aap_oidc_setup_service.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            service = _make_service()
            await service.setup(_make_request(insecure_skip_tls_verify=True))

            mock_cls.assert_called_once_with(verify=False, timeout=30.0)

    @pytest.mark.asyncio
    async def test_tls_verify_enabled_by_default(self) -> None:
        mock_client = AsyncMock()
        mock_client.request.side_effect = [
            MagicMock(status_code=200, json=MagicMock(return_value=_org_response())),
            MagicMock(status_code=201, json=MagicMock(return_value=_app_response())),
        ]

        with patch("syntara.identity_providers.services.aap_oidc_setup_service.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            service = _make_service()
            await service.setup(_make_request())

            mock_cls.assert_called_once_with(verify=True, timeout=30.0)


class TestAAPConnectionErrors:
    """Tests for AAP connection failures."""

    @pytest.mark.asyncio
    @respx.mock
    async def test_connect_error_raises_connection_error(self) -> None:
        respx.get(f"{_AAP_API}/organizations/").mock(side_effect=httpx.ConnectError("refused"))

        service = _make_service()
        with pytest.raises(AAPConnectionError, match="Cannot connect"):
            await service.setup(_make_request())

    @pytest.mark.asyncio
    @respx.mock
    async def test_tls_error_raises_descriptive_message(self) -> None:
        respx.get(f"{_AAP_API}/organizations/").mock(
            side_effect=httpx.ConnectError(
                "[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: self-signed certificate"
            )
        )

        service = _make_service()
        with pytest.raises(AAPConnectionError, match="Disable TLS certificate verification"):
            await service.setup(_make_request())

    @pytest.mark.asyncio
    @respx.mock
    async def test_timeout_raises_connection_error(self) -> None:
        respx.get(f"{_AAP_API}/organizations/").mock(side_effect=httpx.ReadTimeout("timed out"))

        service = _make_service()
        with pytest.raises(AAPConnectionError, match="timed out"):
            await service.setup(_make_request())

    @pytest.mark.asyncio
    @respx.mock
    async def test_request_error_raises_connection_error(self) -> None:
        respx.get(f"{_AAP_API}/organizations/").mock(side_effect=httpx.RequestError("network error"))

        service = _make_service()
        with pytest.raises(AAPConnectionError, match="request failed"):
            await service.setup(_make_request())


class TestAAPAuthErrors:
    """Tests for AAP authentication failures."""

    @pytest.mark.asyncio
    @respx.mock
    async def test_401_raises_authentication_error(self) -> None:
        respx.get(f"{_AAP_API}/organizations/").mock(return_value=httpx.Response(401, json={"detail": "Unauthorized"}))

        service = _make_service()
        with pytest.raises(AAPAuthenticationError, match="authentication failed"):
            await service.setup(_make_request())

    @pytest.mark.asyncio
    @respx.mock
    async def test_403_raises_authorization_error(self) -> None:
        respx.get(f"{_AAP_API}/organizations/").mock(return_value=httpx.Response(403, json={"detail": "Forbidden"}))

        service = _make_service()
        with pytest.raises(AAPAuthenticationError, match="does not have admin privileges"):
            await service.setup(_make_request())


class TestAAPSetupErrors:
    """Tests for AAP setup failures."""

    @pytest.mark.asyncio
    @respx.mock
    async def test_no_organizations_raises_setup_error(self) -> None:
        respx.get(f"{_AAP_API}/organizations/").mock(return_value=httpx.Response(200, json={"count": 0, "results": []}))

        service = _make_service()
        with pytest.raises(AAPSetupError, match="No organization named 'Default'"):
            await service.setup(_make_request())

    @pytest.mark.asyncio
    @respx.mock
    async def test_custom_organization_name(self) -> None:
        respx.get(f"{_AAP_API}/organizations/").mock(
            return_value=httpx.Response(200, json=_org_response(org_id=7, name="Engineering"))
        )
        respx.post(f"{_AAP_API}/applications/").mock(return_value=httpx.Response(201, json=_app_response()))

        service = _make_service()
        await service.setup(_make_request(organization="Engineering"))

    @pytest.mark.asyncio
    @respx.mock
    async def test_nonexistent_organization_raises_setup_error(self) -> None:
        respx.get(f"{_AAP_API}/organizations/").mock(return_value=httpx.Response(200, json={"count": 0, "results": []}))

        service = _make_service()
        with pytest.raises(AAPSetupError, match="No organization named 'DoesNotExist'"):
            await service.setup(_make_request(organization="DoesNotExist"))

    @pytest.mark.asyncio
    @respx.mock
    async def test_app_creation_duplicate_raises_friendly_error(self) -> None:
        respx.get(f"{_AAP_API}/organizations/").mock(return_value=httpx.Response(200, json=_org_response()))
        respx.post(f"{_AAP_API}/applications/").mock(
            return_value=httpx.Response(
                400, json={"non_field_errors": ["The fields name, organization must make a unique set."]}
            )
        )

        service = _make_service()
        with pytest.raises(AAPSetupError, match="already exists"):
            await service.setup(_make_request())

    @pytest.mark.asyncio
    @respx.mock
    async def test_app_creation_500_raises_connection_error(self) -> None:
        respx.get(f"{_AAP_API}/organizations/").mock(return_value=httpx.Response(200, json=_org_response()))
        respx.post(f"{_AAP_API}/applications/").mock(return_value=httpx.Response(500, text="Internal Server Error"))

        service = _make_service()
        with pytest.raises(AAPConnectionError, match="internal error"):
            await service.setup(_make_request())

    @pytest.mark.asyncio
    @respx.mock
    async def test_missing_client_credentials_raises_setup_error(self) -> None:
        respx.get(f"{_AAP_API}/organizations/").mock(return_value=httpx.Response(200, json=_org_response()))
        respx.post(f"{_AAP_API}/applications/").mock(return_value=httpx.Response(201, json={"id": 1, "name": "app"}))

        service = _make_service()
        with pytest.raises(AAPSetupError, match="did not return client credentials"):
            await service.setup(_make_request())

    @pytest.mark.asyncio
    @respx.mock
    async def test_malformed_org_response_raises_setup_error(self) -> None:
        respx.get(f"{_AAP_API}/organizations/").mock(
            return_value=httpx.Response(200, json={"count": 1, "results": [{"name": "no-id"}]})
        )

        service = _make_service()
        with pytest.raises(AAPSetupError, match="Failed to parse organization"):
            await service.setup(_make_request())

    @pytest.mark.asyncio
    @respx.mock
    async def test_invalid_json_response_raises_setup_error(self) -> None:
        respx.get(f"{_AAP_API}/organizations/").mock(
            return_value=httpx.Response(200, text="not json", headers={"content-type": "text/plain"})
        )

        service = _make_service()
        with pytest.raises(AAPSetupError, match="invalid response"):
            await service.setup(_make_request())


class TestOAuth2AppPayload:
    """Tests for the OAuth2 app creation payload sent to AAP."""

    @pytest.mark.asyncio
    @respx.mock
    async def test_sends_correct_app_payload(self) -> None:
        respx.get(f"{_AAP_API}/organizations/").mock(return_value=httpx.Response(200, json=_org_response()))
        app_route = respx.post(f"{_AAP_API}/applications/").mock(return_value=httpx.Response(201, json=_app_response()))

        service = _make_service()
        await service.setup(_make_request())

        import json

        body = json.loads(app_route.calls[0].request.content.decode())
        assert body["name"] == _TEST_PRODUCT_NAME
        assert body["client_type"] == "confidential"
        assert body["authorization_grant_type"] == "authorization-code"
        assert body["algorithm"] == "RS256"
        assert body["skip_authorization"] is True
        assert body["app_url"] == "https://example.com"
        assert "redirect_uris" in body

    @pytest.mark.asyncio
    @respx.mock
    async def test_post_logout_redirect_uris_deduplicated_with_slashes(
        self, override_settings: Callable[..., AbstractContextManager[object]]
    ) -> None:
        respx.get(f"{_AAP_API}/organizations/").mock(return_value=httpx.Response(200, json=_org_response()))
        app_route = respx.post(f"{_AAP_API}/applications/").mock(return_value=httpx.Response(201, json=_app_response()))

        import json

        with override_settings(
            cors_allow_origins=["https://example.com", "https://frontend.example.com"],
        ):
            service = _make_service()
            await service.setup(_make_request())

        body = json.loads(app_route.calls[0].request.content.decode())
        uris = set(body["post_logout_redirect_uris"].split())
        assert uris == {
            "https://frontend.example.com",
            "https://frontend.example.com/",
            "https://example.com",
            "https://example.com/",
        }

    @pytest.mark.asyncio
    @respx.mock
    async def test_uses_basic_auth(self) -> None:
        respx.get(f"{_AAP_API}/organizations/").mock(return_value=httpx.Response(200, json=_org_response()))
        app_route = respx.post(f"{_AAP_API}/applications/").mock(return_value=httpx.Response(201, json=_app_response()))

        service = _make_service()
        await service.setup(_make_request(admin_username="myuser", admin_password="mypass"))  # noqa: S106 -- test fixture

        auth_header = app_route.calls[0].request.headers.get("authorization", "")
        assert auth_header.startswith("Basic ")

    @pytest.mark.asyncio
    @respx.mock
    async def test_uses_bearer_token_with_pat(self) -> None:
        respx.get(f"{_AAP_API}/organizations/").mock(return_value=httpx.Response(200, json=_org_response()))
        app_route = respx.post(f"{_AAP_API}/applications/").mock(return_value=httpx.Response(201, json=_app_response()))

        service = _make_service()
        await service.setup(_make_pat_request(personal_access_token="my-secret-pat"))  # noqa: S106 -- test fixture

        auth_header = app_route.calls[0].request.headers.get("authorization", "")
        assert auth_header == "Bearer my-secret-pat"

    @pytest.mark.asyncio
    @respx.mock
    async def test_pat_creates_idp_with_aap_presets(self) -> None:
        respx.get(f"{_AAP_API}/organizations/").mock(return_value=httpx.Response(200, json=_org_response()))
        respx.post(f"{_AAP_API}/applications/").mock(return_value=httpx.Response(201, json=_app_response()))

        idp_service = _mock_idp_service()
        service = _make_service(idp_service=idp_service)
        await service.setup(_make_pat_request())

        idp_service.create_provider.assert_awaited_once()
        create_arg = idp_service.create_provider.call_args[0][0]
        assert create_arg.name == "Ansible Automation Platform"
        assert create_arg.configuration.idp_type == OIDCIdpType.AAP


class TestAuthMethodValidation:
    """Tests for request model auth method validation."""

    def test_basic_auth_valid(self) -> None:
        request = _make_request(admin_username="admin", admin_password="secret")  # noqa: S106 -- test fixture
        assert request.admin_username == "admin"
        assert request.personal_access_token is None

    def test_pat_auth_valid(self) -> None:
        request = _make_pat_request()
        assert request.personal_access_token == "my-pat-token"  # noqa: S105 -- test assertion
        assert request.admin_username is None

    def test_both_auth_methods_rejected(self) -> None:
        with pytest.raises(ValueError, match="not both"):
            AAPOIDCSetupRequest(
                aap_url=_AAP_URL,
                admin_username="admin",
                admin_password="secret",  # noqa: S106 -- test fixture
                personal_access_token="token",  # noqa: S106 -- test fixture
            )

    def test_no_auth_method_rejected(self) -> None:
        with pytest.raises(ValueError, match=r"admin credentials.*or a personal access token"):
            AAPOIDCSetupRequest(aap_url=_AAP_URL)

    def test_username_without_password_rejected(self) -> None:
        with pytest.raises(ValueError, match="Both admin_username and admin_password"):
            AAPOIDCSetupRequest(aap_url=_AAP_URL, admin_username="admin")
