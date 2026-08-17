from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Literal, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.oidc_claim_mapping import OIDCClaimMapping
    from ..models.oidc_group_mapping_entry import OIDCGroupMappingEntry


T = TypeVar("T", bound="OIDCConfigurationUpdate")


@_attrs_define
class OIDCConfigurationUpdate:
    """Update schema for OIDC configuration (client_secret optional — preserves existing if omitted).

    Attributes:
        issuer_url (str): OIDC issuer URL (e.g. https://accounts.google.com)
        client_id (str): OAuth 2.0 client ID
        redirect_uri (str): OAuth 2.0 redirect URI
        provider_type (Literal['oidc'] | Unset):  Default: 'oidc'.
        idp_type (None | str | Unset): Identity provider type hint. Known values: aap, custom
        auto_discovery (bool | Unset): Use OIDC auto-discovery via .well-known endpoint Default: True.
        client_secret (None | str | Unset): OAuth 2.0 client secret (omit to keep existing)
        scopes (str | Unset): Space-separated list of OAuth 2.0 scopes Default: 'openid profile email'.
        authorization_endpoint (None | str | Unset): Authorization endpoint URL
        token_endpoint (None | str | Unset): Token endpoint URL
        jwks_uri (None | str | Unset): JWKS URI for token verification
        userinfo_endpoint (None | str | Unset): Userinfo endpoint URL (optional)
        end_session_endpoint (None | str | Unset): OIDC end session endpoint URL for RP-initiated logout (omit to keep
            existing)
        enable_rp_initiated_logout (bool | None | Unset): Enable RP-initiated logout redirect to IdP when user logs out
            (omit to keep existing)
        claim_mapping (None | OIDCClaimMapping | Unset): OIDC claim mapping (omit to keep existing)
        group_jmespath_expression (None | str | Unset): JMESPath expression for group extraction (omit to keep existing)
        group_mapping_entries (list[OIDCGroupMappingEntry] | None | Unset): IdP-to-Syntara group mapping entries (omit
            to keep existing)
        allow_all_authenticated (bool | None | Unset): Allow all users from this IdP to log in regardless of group
            mapping results (omit to keep existing)
        aap_role_mapping_enabled (bool | None | Unset): Map Ansible Automation Platform aap_system_role claim to built-
            in groups (omit to keep existing)
        disable_tls_verify (bool | None | Unset): Disable TLS certificate verification for this identity provider (omit
            to keep existing)
    """

    issuer_url: str
    client_id: str
    redirect_uri: str
    provider_type: Literal["oidc"] | Unset = "oidc"
    idp_type: None | str | Unset = UNSET
    auto_discovery: bool | Unset = True
    client_secret: None | str | Unset = UNSET
    scopes: str | Unset = "openid profile email"
    authorization_endpoint: None | str | Unset = UNSET
    token_endpoint: None | str | Unset = UNSET
    jwks_uri: None | str | Unset = UNSET
    userinfo_endpoint: None | str | Unset = UNSET
    end_session_endpoint: None | str | Unset = UNSET
    enable_rp_initiated_logout: bool | None | Unset = UNSET
    claim_mapping: None | OIDCClaimMapping | Unset = UNSET
    group_jmespath_expression: None | str | Unset = UNSET
    group_mapping_entries: list[OIDCGroupMappingEntry] | None | Unset = UNSET
    allow_all_authenticated: bool | None | Unset = UNSET
    aap_role_mapping_enabled: bool | None | Unset = UNSET
    disable_tls_verify: bool | None | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        from ..models.oidc_claim_mapping import OIDCClaimMapping

        issuer_url = self.issuer_url

        client_id = self.client_id

        redirect_uri = self.redirect_uri

        provider_type = self.provider_type

        idp_type: None | str | Unset
        if isinstance(self.idp_type, Unset):
            idp_type = UNSET
        else:
            idp_type = self.idp_type

        auto_discovery = self.auto_discovery

        client_secret: None | str | Unset
        if isinstance(self.client_secret, Unset):
            client_secret = UNSET
        else:
            client_secret = self.client_secret

        scopes = self.scopes

        authorization_endpoint: None | str | Unset
        if isinstance(self.authorization_endpoint, Unset):
            authorization_endpoint = UNSET
        else:
            authorization_endpoint = self.authorization_endpoint

        token_endpoint: None | str | Unset
        if isinstance(self.token_endpoint, Unset):
            token_endpoint = UNSET
        else:
            token_endpoint = self.token_endpoint

        jwks_uri: None | str | Unset
        if isinstance(self.jwks_uri, Unset):
            jwks_uri = UNSET
        else:
            jwks_uri = self.jwks_uri

        userinfo_endpoint: None | str | Unset
        if isinstance(self.userinfo_endpoint, Unset):
            userinfo_endpoint = UNSET
        else:
            userinfo_endpoint = self.userinfo_endpoint

        end_session_endpoint: None | str | Unset
        if isinstance(self.end_session_endpoint, Unset):
            end_session_endpoint = UNSET
        else:
            end_session_endpoint = self.end_session_endpoint

        enable_rp_initiated_logout: bool | None | Unset
        if isinstance(self.enable_rp_initiated_logout, Unset):
            enable_rp_initiated_logout = UNSET
        else:
            enable_rp_initiated_logout = self.enable_rp_initiated_logout

        claim_mapping: dict[str, Any] | None | Unset
        if isinstance(self.claim_mapping, Unset):
            claim_mapping = UNSET
        elif isinstance(self.claim_mapping, OIDCClaimMapping):
            claim_mapping = self.claim_mapping.to_dict()
        else:
            claim_mapping = self.claim_mapping

        group_jmespath_expression: None | str | Unset
        if isinstance(self.group_jmespath_expression, Unset):
            group_jmespath_expression = UNSET
        else:
            group_jmespath_expression = self.group_jmespath_expression

        group_mapping_entries: list[dict[str, Any]] | None | Unset
        if isinstance(self.group_mapping_entries, Unset):
            group_mapping_entries = UNSET
        elif isinstance(self.group_mapping_entries, list):
            group_mapping_entries = []
            for group_mapping_entries_type_0_item_data in self.group_mapping_entries:
                group_mapping_entries_type_0_item = group_mapping_entries_type_0_item_data.to_dict()
                group_mapping_entries.append(group_mapping_entries_type_0_item)

        else:
            group_mapping_entries = self.group_mapping_entries

        allow_all_authenticated: bool | None | Unset
        if isinstance(self.allow_all_authenticated, Unset):
            allow_all_authenticated = UNSET
        else:
            allow_all_authenticated = self.allow_all_authenticated

        aap_role_mapping_enabled: bool | None | Unset
        if isinstance(self.aap_role_mapping_enabled, Unset):
            aap_role_mapping_enabled = UNSET
        else:
            aap_role_mapping_enabled = self.aap_role_mapping_enabled

        disable_tls_verify: bool | None | Unset
        if isinstance(self.disable_tls_verify, Unset):
            disable_tls_verify = UNSET
        else:
            disable_tls_verify = self.disable_tls_verify

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "issuer_url": issuer_url,
                "client_id": client_id,
                "redirect_uri": redirect_uri,
            }
        )
        if provider_type is not UNSET:
            field_dict["provider_type"] = provider_type
        if idp_type is not UNSET:
            field_dict["idp_type"] = idp_type
        if auto_discovery is not UNSET:
            field_dict["auto_discovery"] = auto_discovery
        if client_secret is not UNSET:
            field_dict["client_secret"] = client_secret
        if scopes is not UNSET:
            field_dict["scopes"] = scopes
        if authorization_endpoint is not UNSET:
            field_dict["authorization_endpoint"] = authorization_endpoint
        if token_endpoint is not UNSET:
            field_dict["token_endpoint"] = token_endpoint
        if jwks_uri is not UNSET:
            field_dict["jwks_uri"] = jwks_uri
        if userinfo_endpoint is not UNSET:
            field_dict["userinfo_endpoint"] = userinfo_endpoint
        if end_session_endpoint is not UNSET:
            field_dict["end_session_endpoint"] = end_session_endpoint
        if enable_rp_initiated_logout is not UNSET:
            field_dict["enable_rp_initiated_logout"] = enable_rp_initiated_logout
        if claim_mapping is not UNSET:
            field_dict["claim_mapping"] = claim_mapping
        if group_jmespath_expression is not UNSET:
            field_dict["group_jmespath_expression"] = group_jmespath_expression
        if group_mapping_entries is not UNSET:
            field_dict["group_mapping_entries"] = group_mapping_entries
        if allow_all_authenticated is not UNSET:
            field_dict["allow_all_authenticated"] = allow_all_authenticated
        if aap_role_mapping_enabled is not UNSET:
            field_dict["aap_role_mapping_enabled"] = aap_role_mapping_enabled
        if disable_tls_verify is not UNSET:
            field_dict["disable_tls_verify"] = disable_tls_verify

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.oidc_claim_mapping import OIDCClaimMapping
        from ..models.oidc_group_mapping_entry import OIDCGroupMappingEntry

        d = dict(src_dict)
        issuer_url = d.pop("issuer_url")

        client_id = d.pop("client_id")

        redirect_uri = d.pop("redirect_uri")

        provider_type = cast(Literal["oidc"] | Unset, d.pop("provider_type", UNSET))
        if provider_type != "oidc" and not isinstance(provider_type, Unset):
            raise ValueError(f"provider_type must match const 'oidc', got '{provider_type}'")

        def _parse_idp_type(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        idp_type = _parse_idp_type(d.pop("idp_type", UNSET))

        auto_discovery = d.pop("auto_discovery", UNSET)

        def _parse_client_secret(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        client_secret = _parse_client_secret(d.pop("client_secret", UNSET))

        scopes = d.pop("scopes", UNSET)

        def _parse_authorization_endpoint(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        authorization_endpoint = _parse_authorization_endpoint(d.pop("authorization_endpoint", UNSET))

        def _parse_token_endpoint(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        token_endpoint = _parse_token_endpoint(d.pop("token_endpoint", UNSET))

        def _parse_jwks_uri(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        jwks_uri = _parse_jwks_uri(d.pop("jwks_uri", UNSET))

        def _parse_userinfo_endpoint(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        userinfo_endpoint = _parse_userinfo_endpoint(d.pop("userinfo_endpoint", UNSET))

        def _parse_end_session_endpoint(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        end_session_endpoint = _parse_end_session_endpoint(d.pop("end_session_endpoint", UNSET))

        def _parse_enable_rp_initiated_logout(data: object) -> bool | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(bool | None | Unset, data)

        enable_rp_initiated_logout = _parse_enable_rp_initiated_logout(d.pop("enable_rp_initiated_logout", UNSET))

        def _parse_claim_mapping(data: object) -> None | OIDCClaimMapping | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                claim_mapping_type_0 = OIDCClaimMapping.from_dict(data)

                return claim_mapping_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | OIDCClaimMapping | Unset, data)

        claim_mapping = _parse_claim_mapping(d.pop("claim_mapping", UNSET))

        def _parse_group_jmespath_expression(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        group_jmespath_expression = _parse_group_jmespath_expression(d.pop("group_jmespath_expression", UNSET))

        def _parse_group_mapping_entries(data: object) -> list[OIDCGroupMappingEntry] | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                group_mapping_entries_type_0 = []
                _group_mapping_entries_type_0 = data
                for group_mapping_entries_type_0_item_data in _group_mapping_entries_type_0:
                    group_mapping_entries_type_0_item = OIDCGroupMappingEntry.from_dict(
                        group_mapping_entries_type_0_item_data
                    )

                    group_mapping_entries_type_0.append(group_mapping_entries_type_0_item)

                return group_mapping_entries_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[OIDCGroupMappingEntry] | None | Unset, data)

        group_mapping_entries = _parse_group_mapping_entries(d.pop("group_mapping_entries", UNSET))

        def _parse_allow_all_authenticated(data: object) -> bool | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(bool | None | Unset, data)

        allow_all_authenticated = _parse_allow_all_authenticated(d.pop("allow_all_authenticated", UNSET))

        def _parse_aap_role_mapping_enabled(data: object) -> bool | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(bool | None | Unset, data)

        aap_role_mapping_enabled = _parse_aap_role_mapping_enabled(d.pop("aap_role_mapping_enabled", UNSET))

        def _parse_disable_tls_verify(data: object) -> bool | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(bool | None | Unset, data)

        disable_tls_verify = _parse_disable_tls_verify(d.pop("disable_tls_verify", UNSET))

        oidc_configuration_update = cls(
            issuer_url=issuer_url,
            client_id=client_id,
            redirect_uri=redirect_uri,
            provider_type=provider_type,
            idp_type=idp_type,
            auto_discovery=auto_discovery,
            client_secret=client_secret,
            scopes=scopes,
            authorization_endpoint=authorization_endpoint,
            token_endpoint=token_endpoint,
            jwks_uri=jwks_uri,
            userinfo_endpoint=userinfo_endpoint,
            end_session_endpoint=end_session_endpoint,
            enable_rp_initiated_logout=enable_rp_initiated_logout,
            claim_mapping=claim_mapping,
            group_jmespath_expression=group_jmespath_expression,
            group_mapping_entries=group_mapping_entries,
            allow_all_authenticated=allow_all_authenticated,
            aap_role_mapping_enabled=aap_role_mapping_enabled,
            disable_tls_verify=disable_tls_verify,
        )

        return oidc_configuration_update
