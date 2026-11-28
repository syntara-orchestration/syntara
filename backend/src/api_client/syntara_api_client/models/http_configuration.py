from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

T = TypeVar("T", bound="HTTPConfiguration")


@_attrs_define
class HTTPConfiguration:
    """HTTPS origin for credentialed HTTP workloads.

    Attributes:
        base_url (str): Authorized HTTPS origin for HTTP requests
        allow_http (bool | Unset): Allow HTTP (unencrypted) connections. Loopback addresses are always permitted over
            HTTP. Default: False.
        insecure_skip_tls_verify (bool | Unset): Disable TLS certificate verification for connections to this
            integration. Default: False.
        ca_certificate (None | str | Unset): PEM-encoded CA certificate to trust for this integration's TLS connections.
        integration_type (Literal['http'] | Unset):  Default: 'http'.
    """

    base_url: str
    allow_http: bool | Unset = False
    insecure_skip_tls_verify: bool | Unset = False
    ca_certificate: None | str | Unset = UNSET
    integration_type: Literal["http"] | Unset = "http"

    def to_dict(self) -> dict[str, Any]:
        base_url = self.base_url

        allow_http = self.allow_http

        insecure_skip_tls_verify = self.insecure_skip_tls_verify

        ca_certificate: None | str | Unset
        if isinstance(self.ca_certificate, Unset):
            ca_certificate = UNSET
        else:
            ca_certificate = self.ca_certificate

        integration_type = self.integration_type

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "base_url": base_url,
            }
        )
        if allow_http is not UNSET:
            field_dict["allow_http"] = allow_http
        if insecure_skip_tls_verify is not UNSET:
            field_dict["insecure_skip_tls_verify"] = insecure_skip_tls_verify
        if ca_certificate is not UNSET:
            field_dict["ca_certificate"] = ca_certificate
        if integration_type is not UNSET:
            field_dict["integration_type"] = integration_type

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        base_url = d.pop("base_url")

        allow_http = d.pop("allow_http", UNSET)

        insecure_skip_tls_verify = d.pop("insecure_skip_tls_verify", UNSET)

        def _parse_ca_certificate(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        ca_certificate = _parse_ca_certificate(d.pop("ca_certificate", UNSET))

        integration_type = cast(Literal["http"] | Unset, d.pop("integration_type", UNSET))
        if integration_type != "http" and not isinstance(integration_type, Unset):
            raise ValueError(f"integration_type must match const 'http', got '{integration_type}'")

        http_configuration = cls(
            base_url=base_url,
            allow_http=allow_http,
            insecure_skip_tls_verify=insecure_skip_tls_verify,
            ca_certificate=ca_certificate,
            integration_type=integration_type,
        )

        return http_configuration
