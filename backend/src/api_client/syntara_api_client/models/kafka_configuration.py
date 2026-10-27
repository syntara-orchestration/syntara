from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal, TypeVar, cast

from attrs import define as _attrs_define

from ..models.kafka_sasl_mechanism import KafkaSaslMechanism
from ..models.kafka_security_protocol import KafkaSecurityProtocol
from ..types import UNSET, Unset

T = TypeVar("T", bound="KafkaConfiguration")


@_attrs_define
class KafkaConfiguration:
    """Configuration for a Kafka cluster integration.

    Broker addresses live here. The username and password stay on the
    linked Kafka credential when SASL_SSL is selected. Unauthenticated SSL
    and explicitly opted-in PLAINTEXT do not require a credential.

        Attributes:
            bootstrap_servers (list[str]): Kafka bootstrap servers as host:port (or [ipv6]:port) values.
            allow_http (bool | Unset): Allow HTTP (unencrypted) connections. Loopback addresses are always permitted over
                HTTP. Default: False.
            insecure_skip_tls_verify (bool | Unset): Disable TLS certificate verification for connections to this
                integration. Default: False.
            ca_certificate (None | str | Unset): PEM-encoded CA certificate to trust for this integration's TLS connections.
            integration_type (Literal['kafka'] | Unset):  Default: 'kafka'.
            security_protocol (KafkaSecurityProtocol | Unset): Transport modes that decide whether a Kafka credential is
                required.
            allow_plaintext (bool | Unset): Explicitly allow unauthenticated, unencrypted PLAINTEXT connections. Default:
                False.
            sasl_mechanism (KafkaSaslMechanism | Unset): SASL mechanism used with the Kafka credential username and
                password.

                Cloud brokers such as Aiven use SCRAM-SHA-256. PLAIN remains available
                for clusters that authenticate that way.
    """

    bootstrap_servers: list[str]
    allow_http: bool | Unset = False
    insecure_skip_tls_verify: bool | Unset = False
    ca_certificate: None | str | Unset = UNSET
    integration_type: Literal["kafka"] | Unset = "kafka"
    security_protocol: KafkaSecurityProtocol | Unset = UNSET
    allow_plaintext: bool | Unset = False
    sasl_mechanism: KafkaSaslMechanism | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        bootstrap_servers = self.bootstrap_servers

        allow_http = self.allow_http

        insecure_skip_tls_verify = self.insecure_skip_tls_verify

        ca_certificate: None | str | Unset
        if isinstance(self.ca_certificate, Unset):
            ca_certificate = UNSET
        else:
            ca_certificate = self.ca_certificate

        integration_type = self.integration_type

        security_protocol: str | Unset = UNSET
        if not isinstance(self.security_protocol, Unset):
            security_protocol = self.security_protocol.value

        allow_plaintext = self.allow_plaintext

        sasl_mechanism: str | Unset = UNSET
        if not isinstance(self.sasl_mechanism, Unset):
            sasl_mechanism = self.sasl_mechanism.value

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "bootstrap_servers": bootstrap_servers,
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
        if security_protocol is not UNSET:
            field_dict["security_protocol"] = security_protocol
        if allow_plaintext is not UNSET:
            field_dict["allow_plaintext"] = allow_plaintext
        if sasl_mechanism is not UNSET:
            field_dict["sasl_mechanism"] = sasl_mechanism

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        bootstrap_servers = cast(list[str], d.pop("bootstrap_servers"))

        allow_http = d.pop("allow_http", UNSET)

        insecure_skip_tls_verify = d.pop("insecure_skip_tls_verify", UNSET)

        def _parse_ca_certificate(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        ca_certificate = _parse_ca_certificate(d.pop("ca_certificate", UNSET))

        integration_type = cast(Literal["kafka"] | Unset, d.pop("integration_type", UNSET))
        if integration_type != "kafka" and not isinstance(integration_type, Unset):
            raise ValueError(f"integration_type must match const 'kafka', got '{integration_type}'")

        _security_protocol = d.pop("security_protocol", UNSET)
        security_protocol: KafkaSecurityProtocol | Unset
        if isinstance(_security_protocol, Unset):
            security_protocol = UNSET
        else:
            security_protocol = KafkaSecurityProtocol(_security_protocol)

        allow_plaintext = d.pop("allow_plaintext", UNSET)

        _sasl_mechanism = d.pop("sasl_mechanism", UNSET)
        sasl_mechanism: KafkaSaslMechanism | Unset
        if isinstance(_sasl_mechanism, Unset):
            sasl_mechanism = UNSET
        else:
            sasl_mechanism = KafkaSaslMechanism(_sasl_mechanism)

        kafka_configuration = cls(
            bootstrap_servers=bootstrap_servers,
            allow_http=allow_http,
            insecure_skip_tls_verify=insecure_skip_tls_verify,
            ca_certificate=ca_certificate,
            integration_type=integration_type,
            security_protocol=security_protocol,
            allow_plaintext=allow_plaintext,
            sasl_mechanism=sasl_mechanism,
        )

        return kafka_configuration
