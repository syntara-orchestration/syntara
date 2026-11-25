"""Kafka mutual TLS checks using generated certificates and a local listener."""

import asyncio
import contextlib
import ssl
import stat
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import serialization

from syntara.credentials.exceptions import CredentialValidationError
from syntara.credentials.lib.mtls_identity import (
    MTLS_CERTIFICATE_VAR,
    MTLS_PASSPHRASE_VAR,
    MTLS_PRIVATE_KEY_VAR,
    MTLSIdentityErrorCode,
    validate_mtls_identity,
)
from syntara.integrations.adapters.kafka import KafkaAdapter, KafkaAuthenticationConfigurationError
from syntara.integrations.adapters.kafka_tls import KafkaMTLSContext, KafkaMTLSError, build_kafka_mtls_context
from syntara.integrations.adapters.protocol import HealthCheckErrorType
from syntara.integrations.lib.kafka_connection import PinnedKafkaConnection
from syntara.integrations.models.integration_configuration import KafkaConfiguration
from tests.fixtures.tls import generate_ca, generate_server_cert, generate_service_cert


@dataclass(frozen=True)
class LocalTLSIdentity:
    """One client identity and its local server trust material."""

    authority: str
    server_certificate: Path
    server_key: Path
    client_inputs: dict[str, str]

    def server_context(self, *, trust_client: bool) -> ssl.SSLContext:
        """Require a client certificate and optionally trust the generated issuer."""
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        # TLS 1.2 reports a rejected client identity during the handshake.
        context.maximum_version = ssl.TLSVersion.TLSv1_2
        context.verify_mode = ssl.CERT_REQUIRED
        context.load_cert_chain(self.server_certificate, self.server_key)
        if trust_client:
            context.load_verify_locations(cadata=self.authority)
        return context


@pytest.fixture(scope="module")
def local_tls(tmp_path_factory: pytest.TempPathFactory) -> LocalTLSIdentity:
    """Generate a private issuer and distinct client and server certificates."""
    directory = tmp_path_factory.mktemp("kafka-mtls-fixture")
    issuer_key, issuer_cert = generate_ca(directory)
    generate_server_cert(directory, issuer_key, issuer_cert)
    certificate, key_file = generate_service_cert(directory, issuer_key, issuer_cert, "test client", "client")
    passphrase = "local-tls-fixture-passphrase"  # noqa: S105 - generated test identity only
    private_key = serialization.load_pem_private_key(key_file.read_bytes(), password=None)
    return LocalTLSIdentity(
        authority=issuer_cert.public_bytes(serialization.Encoding.PEM).decode(),
        server_certificate=directory / "server.crt",
        server_key=directory / "server.key",
        client_inputs={
            MTLS_CERTIFICATE_VAR: certificate.read_text(),
            MTLS_PRIVATE_KEY_VAR: private_key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.BestAvailableEncryption(passphrase.encode()),
            ).decode(),
            MTLS_PASSPHRASE_VAR: passphrase,
        },
    )


@pytest.mark.parametrize(
    ("protocol", "skip_tls", "message"),
    [
        ("PLAINTEXT", False, "Select SSL"),
        ("SASL_SSL", False, "Select SSL"),
        ("SSL", True, "Turn on TLS certificate verification"),
    ],
)
def test_client_identity_rejects_incompatible_transport(protocol: str, message: str, *, skip_tls: bool) -> None:
    config = KafkaConfiguration(
        bootstrap_servers=["broker.example:9093"],
        security_protocol=protocol,
        allow_plaintext=protocol == "PLAINTEXT",
        insecure_skip_tls_verify=skip_tls,
    )
    with pytest.raises(KafkaAuthenticationConfigurationError, match=message):
        KafkaAdapter(config).connection_options({MTLS_CERTIFICATE_VAR: "unused identity material"}, 1)


def test_ssl_without_identity_uses_server_only_context() -> None:
    config = KafkaConfiguration(bootstrap_servers=["broker.example:9093"], security_protocol="SSL")
    context = KafkaAdapter(config).connection_options({}, 1)["ssl_context"]
    assert isinstance(context, ssl.SSLContext)
    assert not isinstance(context, KafkaMTLSContext)
    assert context.check_hostname
    assert context.verify_mode == ssl.CERT_REQUIRED


@pytest.mark.parametrize(
    ("field", "value", "code"),
    [
        (MTLS_CERTIFICATE_VAR, "invalid certificate", HealthCheckErrorType.MTLS_INVALID_CLIENT_CERTIFICATE),
        (MTLS_PRIVATE_KEY_VAR, "invalid private key", HealthCheckErrorType.MTLS_INVALID_PRIVATE_KEY),
        (MTLS_PASSPHRASE_VAR, "invalid passphrase", HealthCheckErrorType.MTLS_WRONG_PASSPHRASE),
        (MTLS_CERTIFICATE_VAR, None, HealthCheckErrorType.MTLS_CERTIFICATE_KEY_MISMATCH),
    ],
)
def test_tls_setup_reports_safe_identity_codes(
    local_tls: LocalTLSIdentity, field: str, value: str | None, code: HealthCheckErrorType
) -> None:
    replacement = value if value is not None else local_tls.server_certificate.read_text()
    inputs = {**local_tls.client_inputs, field: replacement}
    with pytest.raises(KafkaMTLSError) as caught:
        build_kafka_mtls_context(local_tls.authority, inputs)
    assert caught.value.code == code
    assert caught.value.__suppress_context__
    assert inputs[MTLS_PRIVATE_KEY_VAR] not in str(caught.value)
    assert inputs[MTLS_PASSPHRASE_VAR] not in str(caught.value)


@pytest.mark.parametrize("passphrase", [None, ""])
def test_encrypted_identity_requires_passphrase(local_tls: LocalTLSIdentity, passphrase: str | None) -> None:
    inputs = local_tls.client_inputs
    with pytest.raises(CredentialValidationError, match="Enter the passphrase for this private key") as caught:
        validate_mtls_identity(inputs[MTLS_CERTIFICATE_VAR], inputs[MTLS_PRIVATE_KEY_VAR], passphrase)

    assert caught.value.code == MTLSIdentityErrorCode.WRONG_PASSPHRASE
    assert inputs[MTLS_PRIVATE_KEY_VAR] not in str(caught.value)


@pytest.mark.parametrize("failure", [None, ssl.SSLError, RuntimeError])
def test_identity_file_permissions_and_cleanup(
    local_tls: LocalTLSIdentity,
    monkeypatch: pytest.MonkeyPatch,
    failure: type[Exception] | None,
) -> None:
    observed: list[Path] = []

    def load_chain(_context: KafkaMTLSContext, certfile: Path, keyfile: str, *, password: str) -> None:
        key_path = Path(keyfile)
        observed.extend((certfile.parent, certfile, key_path))
        assert certfile.parent == key_path.parent
        assert stat.S_IMODE(key_path.parent.stat().st_mode) == 0o700
        assert stat.S_IMODE(key_path.stat().st_mode) == 0o600
        assert certfile.read_text() == local_tls.client_inputs[MTLS_CERTIFICATE_VAR]
        assert key_path.read_text() == local_tls.client_inputs[MTLS_PRIVATE_KEY_VAR]
        assert password == local_tls.client_inputs[MTLS_PASSPHRASE_VAR]
        if failure is not None:
            msg = f"sensitive failure at {key_path}"
            raise failure(msg)

    monkeypatch.setattr(KafkaMTLSContext, "load_cert_chain", load_chain)
    if failure is None:
        context = build_kafka_mtls_context(local_tls.authority, local_tls.client_inputs)
        assert context.check_hostname
        assert context.verify_mode == ssl.CERT_REQUIRED
    else:
        with pytest.raises(KafkaMTLSError) as caught:
            build_kafka_mtls_context(local_tls.authority, local_tls.client_inputs)
        assert caught.value.code == (
            HealthCheckErrorType.MTLS_INVALID_CLIENT_CERTIFICATE
            if failure is ssl.SSLError
            else HealthCheckErrorType.MTLS_HANDSHAKE_FAILED
        )
        assert "sensitive failure" not in str(caught.value)
        assert str(observed[-1]) not in str(caught.value)
    assert len(observed) == 3
    assert all(not path.exists() for path in observed)


@pytest.mark.parametrize(
    ("hostname", "trust_broker", "trust_client", "expected_code"),
    [
        ("localhost", True, True, None),
        ("wrong.example", True, True, HealthCheckErrorType.MTLS_HOSTNAME_MISMATCH),
        ("localhost", False, True, HealthCheckErrorType.MTLS_UNTRUSTED_CA),
        ("localhost", True, False, HealthCheckErrorType.MTLS_HANDSHAKE_FAILED),
    ],
)
async def test_pinned_connection_presents_client_certificate_and_classifies_tls_failures(
    local_tls: LocalTLSIdentity,
    hostname: str,
    *,
    trust_broker: bool,
    trust_client: bool,
    expected_code: HealthCheckErrorType | None,
) -> None:
    peer_certificate: asyncio.Future[bytes] = asyncio.get_running_loop().create_future()

    async def accept(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        tls = writer.get_extra_info("ssl_object")
        try:
            assert tls is not None
            certificate = tls.getpeercert(binary_form=True)
            assert isinstance(certificate, bytes)
            peer_certificate.set_result(certificate)
            await reader.read()
        finally:
            writer.close()
            with contextlib.suppress(OSError):
                await writer.wait_closed()

    async with await asyncio.start_server(
        accept, "127.0.0.1", 0, ssl=local_tls.server_context(trust_client=trust_client)
    ) as server:
        port = server.sockets[0].getsockname()[1]
        config = KafkaConfiguration(
            bootstrap_servers=[f"{hostname}:{port}"],
            security_protocol="SSL",
            ca_certificate=local_tls.authority if trust_broker else None,
        )
        options = KafkaAdapter(config).connection_options(local_tls.client_inputs, 3)
        connection = PinnedKafkaConnection(hostname, port, **options)
        with (
            patch(
                "syntara.integrations.lib.kafka_connection.approved_broker_addresses",
                new=AsyncMock(return_value=["127.0.0.1"]),
            ),
            patch.object(connection, "_do_version_lookup", new=AsyncMock()),
        ):
            try:
                if expected_code is None:
                    await connection.connect()
                    certificate = x509.load_pem_x509_certificate(local_tls.client_inputs[MTLS_CERTIFICATE_VAR].encode())
                    assert await asyncio.wait_for(peer_certificate, 3) == certificate.public_bytes(
                        serialization.Encoding.DER
                    )
                else:
                    with pytest.raises(KafkaMTLSError) as caught:
                        await connection.connect()
                    assert caught.value.code == expected_code
                    assert caught.value.__cause__ is None
                    assert hostname not in str(caught.value)
            finally:
                closed = connection.close()
                if closed is not None and not closed.cancelled():
                    await asyncio.wait_for(closed, 3)
