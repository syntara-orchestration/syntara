"""Local certificate rendering only; this does not verify live broker TLS."""

from cryptography import x509

from tools import generate_certs


def test_disposable_kafka_certificate_has_advertised_names_and_java_pem_format(tmp_path, monkeypatch):
    monkeypatch.setattr(generate_certs, "CERTS_DIR", tmp_path)
    ca_key, ca_cert = generate_certs.generate_ca()
    generate_certs.generate_service_cert(ca_key, ca_cert, "kafka", "kafka.local", ["kafka"])
    cert = x509.load_pem_x509_certificate((tmp_path / "kafka.crt").read_bytes())
    sans = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    assert set(sans.get_values_for_type(x509.DNSName)) == {"kafka", "localhost"}
    # Kafka's Java PEM reader needs PKCS#8; S2S service identities are unchanged.
    assert (tmp_path / "kafka.key").read_text().startswith("-----BEGIN PRIVATE KEY-----")
    assert all(filename != "kafka" for filename, _, _ in generate_certs.SERVICE_CERTS)
    assert generate_certs._missing_service_certs([("kafka", "kafka.local", ["kafka"])]) == []
    (tmp_path / "kafka.key").unlink()
    assert generate_certs._missing_service_certs([("kafka", "kafka.local", ["kafka"])])
