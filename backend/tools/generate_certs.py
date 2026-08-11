#!/usr/bin/env python3
"""Generate self-signed TLS certificates for local development.

Creates a CA and per-service certificates for mTLS between Nexus services
running in podman-compose. Each service gets a distinct CN matching the
production naming convention (e.g., backend.ao.svc, worker.ao.svc) so the
auth middleware can extract per-service identity from the client cert.

Certificates are stored in .secrets/certs/ and mounted into containers
via podman-compose.yml volume definitions.

Usage:
    uv run python tools/generate_certs.py          # Generate missing certs
    uv run python tools/generate_certs.py --force   # Regenerate all
"""

from __future__ import annotations

import argparse
import shutil
import stat
import sys
from datetime import UTC, datetime, timedelta
from ipaddress import IPv4Address
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CERTS_DIR = PROJECT_ROOT / ".secrets" / "certs"

VALIDITY_DAYS = 365

# (filename, common_name, dns_sans) — dns_sans are compose service names
# that resolve within the podman network.
SERVICE_CERTS = [
    ("backend", "backend.ao.svc", ["syntara"]),
    ("worker", "worker.ao.svc", ["temporal-worker"]),
    ("background-worker", "background-worker.ao.svc", ["temporal-background-worker"]),
    ("temporal", "temporal.ao.svc", ["temporal"]),
]

# Validate against the canonical list in principal.py
from syntara.core.models.principal import KNOWN_SERVICE_CNS  # noqa: E402

_cert_cns = {cn for _, cn, _ in SERVICE_CERTS}
_expected = set(KNOWN_SERVICE_CNS)
if _cert_cns != _expected:
    msg = f"SERVICE_CERTS CNs {_cert_cns} do not match KNOWN_SERVICE_CNS {_expected}"
    raise RuntimeError(msg)


def _write_key(path: Path, key: rsa.RSAPrivateKey) -> None:
    path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),
        )
    )
    # 644 — containers run as non-root and need to read mounted key files
    path.chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH)


def _write_cert(path: Path, cert: x509.Certificate) -> None:
    path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    path.chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH)  # 644


def _clear_path(path: Path) -> None:
    """Remove a path so it can be replaced by a cert/key file.

    Podman creates empty directories when bind-mounting a missing host path;
    those stubs block later writes with IsADirectoryError.
    """
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.is_dir():
        shutil.rmtree(path)


def generate_ca() -> tuple[rsa.RSAPrivateKey, x509.Certificate]:
    """Generate a self-signed CA certificate and key."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Syntara Dev CA")])
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.now(UTC))
        .not_valid_after(datetime.now(UTC) + timedelta(days=VALIDITY_DAYS))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
        .add_extension(
            x509.KeyUsage(
                digital_signature=False,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=True,
                crl_sign=True,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .sign(key, hashes.SHA256())
    )
    _clear_path(CERTS_DIR / "ca.pem")
    _clear_path(CERTS_DIR / "ca.key")
    _write_cert(CERTS_DIR / "ca.pem", cert)
    _write_key(CERTS_DIR / "ca.key", key)
    return key, cert


def _load_existing_ca() -> tuple[rsa.RSAPrivateKey, x509.Certificate]:
    """Load the existing local-dev CA from disk."""
    ca_cert = x509.load_pem_x509_certificate((CERTS_DIR / "ca.pem").read_bytes())
    loaded = serialization.load_pem_private_key(
        (CERTS_DIR / "ca.key").read_bytes(),
        password=None,
    )
    if not isinstance(loaded, rsa.RSAPrivateKey):
        msg = f"Expected RSA CA key at {CERTS_DIR / 'ca.key'}, got {type(loaded).__name__}"
        raise TypeError(msg)
    return loaded, ca_cert


def generate_service_cert(
    ca_key: rsa.RSAPrivateKey,
    ca_cert: x509.Certificate,
    filename: str,
    common_name: str,
    dns_sans: list[str],
) -> None:
    """Generate a CA-signed service certificate with serverAuth and clientAuth EKUs."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])
    san_entries: list[x509.GeneralName] = [x509.DNSName(name) for name in [*dns_sans, "localhost"]]
    san_entries.append(x509.IPAddress(IPv4Address("127.0.0.1")))

    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(ca_cert.subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.now(UTC))
        .not_valid_after(datetime.now(UTC) + timedelta(days=VALIDITY_DAYS))
        .add_extension(x509.SubjectAlternativeName(san_entries), critical=False)
        .add_extension(
            x509.ExtendedKeyUsage(
                [
                    x509.oid.ExtendedKeyUsageOID.SERVER_AUTH,
                    x509.oid.ExtendedKeyUsageOID.CLIENT_AUTH,
                ]
            ),
            critical=False,
        )
        .add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()),
            critical=False,
        )
        .sign(ca_key, hashes.SHA256())
    )
    cert_path = CERTS_DIR / f"{filename}.crt"
    key_path = CERTS_DIR / f"{filename}.key"
    _clear_path(cert_path)
    _clear_path(key_path)
    _write_cert(cert_path, cert)
    _write_key(key_path, key)


def _missing_service_certs() -> list[tuple[str, str, list[str]]]:
    """Return SERVICE_CERTS entries whose cert or key file is missing or not a file."""
    missing: list[tuple[str, str, list[str]]] = []
    for filename, cn, sans in SERVICE_CERTS:
        cert_path = CERTS_DIR / f"{filename}.crt"
        key_path = CERTS_DIR / f"{filename}.key"
        if not cert_path.is_file() or not key_path.is_file():
            missing.append((filename, cn, sans))
    return missing


def _chmod_public_certs() -> None:
    """Ensure cert files (not keys) are readable for container volume mounts."""
    for path in CERTS_DIR.iterdir():
        if path.is_file() and not path.name.endswith(".key"):
            current = path.stat().st_mode
            path.chmod(current | stat.S_IRGRP | stat.S_IROTH)


def main() -> None:
    """Generate self-signed CA and per-service TLS certificates for local development."""
    parser = argparse.ArgumentParser(description="Generate TLS certificates for local development")
    parser.add_argument("--force", "-f", action="store_true", help="Regenerate all certificates")
    args = parser.parse_args()

    CERTS_DIR.mkdir(parents=True, exist_ok=True)
    CERTS_DIR.chmod(stat.S_IRWXU)  # 700

    ca_pem = CERTS_DIR / "ca.pem"
    ca_key_path = CERTS_DIR / "ca.key"

    if args.force or not ca_pem.is_file() or not ca_key_path.is_file():
        print("[INFO] Generating CA certificate...")
        ca_key, ca_cert = generate_ca()
        print(f"  CA cert: {ca_pem}")
        for filename, cn, sans in SERVICE_CERTS:
            print(f"[INFO] Generating {filename} certificate (CN={cn})...")
            generate_service_cert(ca_key, ca_cert, filename, cn, sans)
            print(f"  Cert: {CERTS_DIR / f'{filename}.crt'}")
    else:
        missing = _missing_service_certs()
        if not missing:
            print("[INFO] Certificates already exist, skipping (use --force to regenerate)")
            return

        print(f"[INFO] Backfilling {len(missing)} missing service certificate(s) under existing CA...")
        ca_key, ca_cert = _load_existing_ca()
        for filename, cn, sans in missing:
            print(f"[INFO] Generating {filename} certificate (CN={cn})...")
            generate_service_cert(ca_key, ca_cert, filename, cn, sans)
            print(f"  Cert: {CERTS_DIR / f'{filename}.crt'}")

    _chmod_public_certs()

    print()
    print(f"[INFO] TLS certificates ready in {CERTS_DIR}")
    print("[INFO] Services: backend, worker, background-worker, temporal")


if __name__ == "__main__":
    sys.exit(main() or 0)
