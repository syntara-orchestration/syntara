from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

T = TypeVar("T", bound="OpenShiftConfiguration")


@_attrs_define
class OpenShiftConfiguration:
    """Non-secret connection settings for an OpenShift cluster.

    Attributes:
        base_url (str): OpenShift Kubernetes API URL
        namespace (str): Namespace reserved for future execution workloads
        integration_type (Literal['openshift'] | Unset):  Default: 'openshift'.
        allow_http (bool | Unset): Allow HTTP (unencrypted) connections. Loopback addresses are always permitted over
            HTTP. Default: False.
        insecure_skip_tls_verify (bool | Unset): Disable TLS certificate verification for connections to this
            integration. Default: False.
        ca_certificate (None | str | Unset): PEM-encoded CA certificate to trust for this integration's TLS connections.
    """

    base_url: str
    namespace: str
    integration_type: Literal["openshift"] | Unset = "openshift"
    allow_http: bool | Unset = False
    insecure_skip_tls_verify: bool | Unset = False
    ca_certificate: None | str | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        base_url = self.base_url

        namespace = self.namespace

        integration_type = self.integration_type

        allow_http = self.allow_http

        insecure_skip_tls_verify = self.insecure_skip_tls_verify

        ca_certificate: None | str | Unset
        if isinstance(self.ca_certificate, Unset):
            ca_certificate = UNSET
        else:
            ca_certificate = self.ca_certificate

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "base_url": base_url,
                "namespace": namespace,
            }
        )
        if integration_type is not UNSET:
            field_dict["integration_type"] = integration_type
        if allow_http is not UNSET:
            field_dict["allow_http"] = allow_http
        if insecure_skip_tls_verify is not UNSET:
            field_dict["insecure_skip_tls_verify"] = insecure_skip_tls_verify
        if ca_certificate is not UNSET:
            field_dict["ca_certificate"] = ca_certificate

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        base_url = d.pop("base_url")

        namespace = d.pop("namespace")

        integration_type = cast(Literal["openshift"] | Unset, d.pop("integration_type", UNSET))
        if integration_type != "openshift" and not isinstance(integration_type, Unset):
            raise ValueError(f"integration_type must match const 'openshift', got '{integration_type}'")

        allow_http = d.pop("allow_http", UNSET)

        insecure_skip_tls_verify = d.pop("insecure_skip_tls_verify", UNSET)

        def _parse_ca_certificate(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        ca_certificate = _parse_ca_certificate(d.pop("ca_certificate", UNSET))

        openshift_configuration = cls(
            base_url=base_url,
            namespace=namespace,
            integration_type=integration_type,
            allow_http=allow_http,
            insecure_skip_tls_verify=insecure_skip_tls_verify,
            ca_certificate=ca_certificate,
        )

        return openshift_configuration
