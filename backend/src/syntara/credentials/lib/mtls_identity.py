"""Validate certificate-based client identities without opening a connection."""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING

from cryptography import x509
from cryptography.exceptions import UnsupportedAlgorithm
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat, load_pem_private_key

from syntara.credentials.exceptions import CredentialValidationError

if TYPE_CHECKING:
    from collections.abc import Mapping

    from cryptography.hazmat.primitives.asymmetric.types import PrivateKeyTypes

MTLS_CERTIFICATE_VAR = "mtls_client_certificate"
MTLS_PRIVATE_KEY_VAR = "mtls_client_private_key"
MTLS_PASSPHRASE_VAR = "mtls_client_key_passphrase"  # noqa: S105 - injector key name
MTLS_IDENTITY_VARS = frozenset({MTLS_CERTIFICATE_VAR, MTLS_PRIVATE_KEY_VAR, MTLS_PASSPHRASE_VAR})
MTLS_PASSPHRASE_MIN_LENGTH = 4  # Match the workflow output scrubber's minimum.


class MTLSIdentityErrorCode(StrEnum):
    """Identify which part of a client identity needs correction."""

    INVALID_CLIENT_CERTIFICATE = "MTLS_INVALID_CLIENT_CERTIFICATE"
    INVALID_PRIVATE_KEY = "MTLS_INVALID_PRIVATE_KEY"
    WRONG_PASSPHRASE = "MTLS_WRONG_PASSPHRASE"  # noqa: S105 - error code, not a secret
    CERTIFICATE_KEY_MISMATCH = "MTLS_CERTIFICATE_KEY_MISMATCH"


def mtls_identity_vars(extra_vars: Mapping[str, object]) -> dict[str, str]:
    """Keep the identity keys present so an incomplete identity fails closed."""
    return {name: value if isinstance(value := extra_vars.get(name), str) else "" for name in MTLS_IDENTITY_VARS}


def _load_private_key(pem_key: str, password: bytes | None) -> PrivateKeyTypes:
    try:
        return load_pem_private_key(pem_key.encode(), password=password)
    except TypeError:
        msg = (
            "Enter the passphrase for this private key."
            if password is None
            else "Leave the key passphrase empty for an unencrypted private key."
        )
        raise CredentialValidationError(msg, code=MTLSIdentityErrorCode.WRONG_PASSPHRASE) from None
    except ValueError:
        if password is not None:
            # A protected key can fail with ValueError for a wrong password or
            # unreadable PEM. Trying without a password distinguishes bad PEM.
            try:
                load_pem_private_key(pem_key.encode(), password=None)
            except TypeError:
                msg = "The key passphrase could not open the private key."
                raise CredentialValidationError(msg, code=MTLSIdentityErrorCode.WRONG_PASSPHRASE) from None
            except (ValueError, UnsupportedAlgorithm):
                pass
    except UnsupportedAlgorithm:
        pass
    msg = "Enter a valid PEM private key."
    raise CredentialValidationError(msg, code=MTLSIdentityErrorCode.INVALID_PRIVATE_KEY) from None


def validate_mtls_identity(certificate: object, private_key: object, passphrase: object = None) -> None:
    """Check the PEM inputs, passphrase, and certificate/key match in memory."""
    if not isinstance(certificate, str) or not certificate.strip():
        msg = "The client_certificate field is required."
        raise CredentialValidationError(msg, code=MTLSIdentityErrorCode.INVALID_CLIENT_CERTIFICATE)
    if not isinstance(private_key, str) or not private_key.strip():
        msg = "The client_private_key field is required."
        raise CredentialValidationError(msg, code=MTLSIdentityErrorCode.INVALID_PRIVATE_KEY)

    try:
        leaf = x509.load_pem_x509_certificates(certificate.encode())[0]
        certificate_public_key = leaf.public_key().public_bytes(Encoding.DER, PublicFormat.SubjectPublicKeyInfo)
    except (ValueError, UnsupportedAlgorithm, x509.InvalidVersion):
        msg = "Enter a valid PEM client certificate."
        raise CredentialValidationError(msg, code=MTLSIdentityErrorCode.INVALID_CLIENT_CERTIFICATE) from None

    password = None
    if passphrase not in (None, ""):
        if not isinstance(passphrase, str) or len(passphrase) < MTLS_PASSPHRASE_MIN_LENGTH:
            msg = f"The key passphrase must be at least {MTLS_PASSPHRASE_MIN_LENGTH} characters."
            raise CredentialValidationError(msg, code=MTLSIdentityErrorCode.WRONG_PASSPHRASE)
        try:
            password = passphrase.encode()
        except UnicodeEncodeError:
            msg = "Enter a valid key passphrase."
            raise CredentialValidationError(msg, code=MTLSIdentityErrorCode.WRONG_PASSPHRASE) from None

    key = _load_private_key(private_key, password)
    if key.public_key().public_bytes(Encoding.DER, PublicFormat.SubjectPublicKeyInfo) != certificate_public_key:
        msg = "The private key must match the client certificate."
        raise CredentialValidationError(msg, code=MTLSIdentityErrorCode.CERTIFICATE_KEY_MISMATCH)
