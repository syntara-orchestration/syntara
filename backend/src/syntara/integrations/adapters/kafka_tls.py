"""Build and classify Kafka mutual TLS connections without exposing credentials."""

from __future__ import annotations

import ssl
from pathlib import Path
from tempfile import NamedTemporaryFile, TemporaryDirectory
from typing import TYPE_CHECKING, cast

from syntara.core.exceptions import SyntaraError
from syntara.credentials.exceptions import CredentialValidationError
from syntara.credentials.lib.mtls_identity import (
    MTLS_CERTIFICATE_VAR,
    MTLS_PASSPHRASE_VAR,
    MTLS_PRIVATE_KEY_VAR,
    MTLSIdentityErrorCode,
    validate_mtls_identity,
)
from syntara.integrations.adapters.protocol import HealthCheckErrorType

if TYPE_CHECKING:
    from collections.abc import Mapping

KAFKA_MTLS_ERROR_MESSAGES = {
    HealthCheckErrorType.MTLS_UNTRUSTED_CA: "The broker's certificate authority could not be verified.",
    HealthCheckErrorType.MTLS_INVALID_CLIENT_CERTIFICATE: "The client certificate is invalid.",
    HealthCheckErrorType.MTLS_INVALID_PRIVATE_KEY: "The client private key is invalid.",
    HealthCheckErrorType.MTLS_WRONG_PASSPHRASE: "The key passphrase could not open the private key.",
    HealthCheckErrorType.MTLS_CERTIFICATE_KEY_MISMATCH: "The private key must match the client certificate.",
    HealthCheckErrorType.MTLS_HOSTNAME_MISMATCH: "The broker hostname does not match its certificate.",
    HealthCheckErrorType.MTLS_HANDSHAKE_FAILED: "The mutual TLS connection could not be established.",
}

_IDENTITY_HEALTH_CHECK_ERRORS: dict[str, HealthCheckErrorType] = {
    MTLSIdentityErrorCode.INVALID_CLIENT_CERTIFICATE: HealthCheckErrorType.MTLS_INVALID_CLIENT_CERTIFICATE,
    MTLSIdentityErrorCode.INVALID_PRIVATE_KEY: HealthCheckErrorType.MTLS_INVALID_PRIVATE_KEY,
    MTLSIdentityErrorCode.WRONG_PASSPHRASE: HealthCheckErrorType.MTLS_WRONG_PASSPHRASE,
    MTLSIdentityErrorCode.CERTIFICATE_KEY_MISMATCH: HealthCheckErrorType.MTLS_CERTIFICATE_KEY_MISMATCH,
}

# OpenSSL X509_V_ERR_* values used by SSLCertVerificationError.verify_code.
_HOSTNAME_VERIFY_ERRORS = frozenset({62, 64})  # Hostname and IP address mismatch.
_UNTRUSTED_CA_VERIFY_ERRORS = frozenset({2, 18, 19, 20, 21, 27, 28, 79})


class KafkaMTLSError(SyntaraError):
    """Retain a safe TLS code across the Kafka client connection boundary."""

    def __init__(self, code: HealthCheckErrorType) -> None:
        """Attach a fixed message selected by the TLS code."""
        self.code = code
        super().__init__(KAFKA_MTLS_ERROR_MESSAGES[code])


class KafkaMTLSContext(ssl.SSLContext):
    """Mark client-identity contexts so failures are sanitized only for mTLS."""


def classify_kafka_mtls_failure(error: BaseException, *, during_socket_setup: bool) -> KafkaMTLSError | None:
    """Classify TLS alerts and peer resets during socket setup."""
    tls_error = error if isinstance(error, ssl.SSLError) else error.__cause__
    if isinstance(tls_error, ssl.SSLCertVerificationError):
        verify_code = getattr(tls_error, "verify_code", None)
        if verify_code in _HOSTNAME_VERIFY_ERRORS:
            return KafkaMTLSError(HealthCheckErrorType.MTLS_HOSTNAME_MISMATCH)
        if verify_code in _UNTRUSTED_CA_VERIFY_ERRORS:
            return KafkaMTLSError(HealthCheckErrorType.MTLS_UNTRUSTED_CA)
    if isinstance(tls_error, ssl.SSLError) or (during_socket_setup and isinstance(error, ConnectionResetError)):
        return KafkaMTLSError(HealthCheckErrorType.MTLS_HANDSHAKE_FAILED)
    return None


def build_kafka_mtls_context(ca_certificate: str | None, resolved_credential: Mapping[str, object]) -> KafkaMTLSContext:
    """Load a validated client identity into a hostname-verifying TLS context."""
    certificate = resolved_credential.get(MTLS_CERTIFICATE_VAR)
    private_key = resolved_credential.get(MTLS_PRIVATE_KEY_VAR)
    passphrase = resolved_credential.get(MTLS_PASSPHRASE_VAR)
    try:
        validate_mtls_identity(certificate, private_key, passphrase)
    except CredentialValidationError as exc:
        code = _IDENTITY_HEALTH_CHECK_ERRORS.get(exc.code, HealthCheckErrorType.MTLS_HANDSHAKE_FAILED)
        raise KafkaMTLSError(code) from None

    context = KafkaMTLSContext(ssl.PROTOCOL_TLS_CLIENT)
    context.verify_flags |= ssl.VERIFY_X509_STRICT | ssl.VERIFY_X509_PARTIAL_CHAIN
    try:
        context.load_default_certs()
        if ca_certificate:
            context.load_verify_locations(cadata=ca_certificate)
    except (OSError, ValueError):
        raise KafkaMTLSError(HealthCheckErrorType.MTLS_UNTRUSTED_CA) from None

    try:
        with TemporaryDirectory(prefix="syntara-mtls-") as directory:
            certificate_path = Path(directory) / "certificate.pem"
            certificate_path.write_text(cast("str", certificate), encoding="utf-8")
            # NamedTemporaryFile creates the key with owner-only permissions.
            with NamedTemporaryFile(mode="w", encoding="utf-8", dir=directory, delete=False) as key_file:
                key_file.write(cast("str", private_key))
            try:
                context.load_cert_chain(
                    certificate_path, key_file.name, password=cast("str | None", passphrase or None)
                )
            except ssl.SSLError as exc:
                code = (
                    HealthCheckErrorType.MTLS_CERTIFICATE_KEY_MISMATCH
                    if getattr(exc, "reason", None) == "KEY_VALUES_MISMATCH"
                    else HealthCheckErrorType.MTLS_INVALID_CLIENT_CERTIFICATE
                )
                raise KafkaMTLSError(code) from None
            except (TypeError, ValueError):
                raise KafkaMTLSError(HealthCheckErrorType.MTLS_WRONG_PASSPHRASE) from None
    except KafkaMTLSError:
        raise
    except Exception:  # noqa: BLE001 - never expose unexpected local file or key-loading failures
        raise KafkaMTLSError(HealthCheckErrorType.MTLS_HANDSHAKE_FAILED) from None
    return context
