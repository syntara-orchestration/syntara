"""Tests for local development certificate generation."""

from datetime import UTC, datetime, timedelta

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from syntara.core.config.base import get_settings
from syntara.core.models.principal import KNOWN_SERVICE_CNS
from tools import generate_certs
from tools.generate_certs import SERVICE_CERTS, _missing_service_certs


def test_service_certs_cover_all_known_service_identities() -> None:
    """Certificate generation may include local-only identities beyond built-ins."""
    certificate_cns = {common_name for _, common_name, _ in SERVICE_CERTS}

    assert set(KNOWN_SERVICE_CNS).issubset(certificate_cns)
    assert certificate_cns - set(KNOWN_SERVICE_CNS) == {get_settings().ep_callback_service_cn}
    assert get_settings().ep_callback_service_cn == "execution-plane-callback.ao.svc"


def test_existing_certificate_with_changed_cn_is_regenerated(tmp_path, monkeypatch) -> None:
    """A certificate with the expected SAN but an old CN must be replaced."""
    entry = next(item for item in SERVICE_CERTS if item[0] == "execution-plane")
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "execution-plane.ao.svc")])
    certificate = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.now(UTC))
        .not_valid_after(datetime.now(UTC) + timedelta(days=1))
        .add_extension(
            x509.SubjectAlternativeName([x509.DNSName(name) for name in entry[2]]),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )
    (tmp_path / "execution-plane.crt").write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    (tmp_path / "execution-plane.key").write_bytes(b"placeholder")
    monkeypatch.setattr(generate_certs, "CERTS_DIR", tmp_path)

    assert entry in _missing_service_certs()
