"""TLS certificate generation helpers for unit and integration tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from syntara.core.tls.certs import generate_ca, generate_service_cert

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

__all__ = [
    "generate_ca",
    "generate_crl",
    "generate_self_signed_cert",
    "generate_server_cert",
    "generate_service_cert",
]


def generate_self_signed_cert(certs_dir: Path, common_name: str, filename: str) -> tuple[Path, Path]:
    """Generate a self-signed certificate and key (for client cert or simple CA tests)."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.now(UTC))
        .not_valid_after(datetime.now(UTC) + timedelta(days=1))
        .sign(key, hashes.SHA256())
    )
    cert_path = certs_dir / f"{filename}.pem"
    key_path = certs_dir / f"{filename}.key"
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL, serialization.NoEncryption()
        )
    )
    return cert_path, key_path


def generate_server_cert(
    certs_dir: Path,
    ca_key: rsa.RSAPrivateKey,
    ca_cert: x509.Certificate,
) -> None:
    """Generate a server certificate signed by *ca_key*/*ca_cert* with localhost SAN."""
    from ipaddress import IPv4Address

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(ca_cert.subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.now(UTC))
        .not_valid_after(datetime.now(UTC) + timedelta(days=1))
        .add_extension(
            x509.SubjectAlternativeName([x509.DNSName("localhost"), x509.IPAddress(IPv4Address("127.0.0.1"))]),
            critical=False,
        )
        .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), critical=False)
        .sign(ca_key, hashes.SHA256())
    )
    (certs_dir / "server.crt").write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    server_key_path = certs_dir / "server.key"
    server_key_path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL, serialization.NoEncryption()
        )
    )


def generate_crl(
    certs_dir: Path,
    ca_key: rsa.RSAPrivateKey,
    ca_cert: x509.Certificate,
    revoked_certs: Sequence[x509.Certificate] | None = None,
) -> Path:
    """Generate a PEM-encoded CRL signed by *ca_key*/*ca_cert*.

    Each certificate in *revoked_certs* is added as a revoked entry.
    Returns the path to the written CRL file.
    """
    builder = (
        x509.CertificateRevocationListBuilder()
        .issuer_name(ca_cert.subject)
        .last_update(datetime.now(UTC))
        .next_update(datetime.now(UTC) + timedelta(days=1))
    )
    for cert in revoked_certs or ():
        builder = builder.add_revoked_certificate(
            x509.RevokedCertificateBuilder()
            .serial_number(cert.serial_number)
            .revocation_date(datetime.now(UTC))
            .build()
        )
    crl = builder.sign(ca_key, hashes.SHA256())
    crl_path = certs_dir / "crl.pem"
    crl_path.write_bytes(crl.public_bytes(serialization.Encoding.PEM))
    return crl_path
