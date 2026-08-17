"""Generate TLS certificates for local development with mTLS enabled.

Produces a CA and per-service certificates (backend, worker) suitable for
use with podman-compose or direct uvicorn invocation.

Usage::

    uv run python scripts/generate_local_certs.py [--output-dir ./certs]
"""

from __future__ import annotations

import argparse
from pathlib import Path

from syntara.core.tls.certs import generate_ca, generate_service_cert

_VALIDITY_DAYS = 365


def generate_local_certs(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    ca_key, ca_cert = generate_ca(output_dir, common_name="Orchestrator Local Dev CA", validity_days=_VALIDITY_DAYS)

    not_valid_before = ca_cert.not_valid_before_utc
    not_valid_after = ca_cert.not_valid_after_utc

    generate_service_cert(
        output_dir,
        ca_key,
        ca_cert,
        common_name="backend.orchestrator.svc",
        filename="backend",
        not_valid_before=not_valid_before,
        not_valid_after=not_valid_after,
    )
    generate_service_cert(
        output_dir,
        ca_key,
        ca_cert,
        common_name="worker.orchestrator.svc",
        filename="worker",
        not_valid_before=not_valid_before,
        not_valid_after=not_valid_after,
    )

    print(f"Certificates generated in {output_dir}/")
    print()
    print("Set the following environment variables:")
    print("  APP_TLS_ENABLED=true")
    print(f"  APP_S2S_TLS_CA_CERT_PATH={output_dir}/ca.pem")
    print(f"  APP_S2S_TLS_CERT_PATH={output_dir}/backend.crt")
    print(f"  APP_S2S_TLS_KEY_PATH={output_dir}/backend.key")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate TLS certificates for local development")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("certs"),
        help="Directory to write certificates to (default: ./certs)",
    )
    args = parser.parse_args()
    generate_local_certs(args.output_dir)


if __name__ == "__main__":
    main()
