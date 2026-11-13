"""Tests for local development certificate generation."""

from syntara.core.models.principal import KNOWN_SERVICE_CNS
from tools.generate_certs import SERVICE_CERTS


def test_service_certs_cover_all_known_service_identities() -> None:
    """Certificate generation may include local-only identities beyond built-ins."""
    certificate_cns = {common_name for _, common_name, _ in SERVICE_CERTS}

    assert set(KNOWN_SERVICE_CNS).issubset(certificate_cns)
    assert certificate_cns - set(KNOWN_SERVICE_CNS) == {"execution-plane.ao.svc"}
