"""Create or refresh the local Syntara OpenShift integration via public APIs.

The ServiceAccount token is submitted as a managed HTTP Bearer Token credential;
the integration configuration and printed output contain no token material.
"""
# ruff: noqa: INP001, EM101, EM102, TRY003, T201

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any
from uuid import UUID

import httpx


def _resources(client: httpx.Client, path: str) -> list[dict[str, Any]]:
    response = client.get(path, params={"limit": 100})
    response.raise_for_status()
    return response.json()["resources"]


def _by_name(resources: list[dict[str, Any]], name: str) -> dict[str, Any] | None:
    return next((resource for resource in resources if resource["name"] == name), None)


def _upsert_credential(client: httpx.Client, project_id: str, token: str) -> str:
    name = "OpenShift execution-plane ServiceAccount"
    credential_type = _by_name(_resources(client, "/api/v1/credential_types"), "HTTP Bearer Token")
    if credential_type is None:
        raise RuntimeError("HTTP Bearer Token credential type is not seeded")
    existing = _by_name(_resources(client, "/api/v1/credentials"), name)
    if existing is not None:
        response = client.patch(f"/api/v1/credentials/{existing['id']}", json={"inputs": {"token": token}})
    else:
        response = client.post(
            "/api/v1/credentials",
            json={
                "name": name,
                "description": (
                    "Short-lived ServiceAccount token for ep-dev-workers; "
                    "rotate with setup-openshift-dev.sh"
                ),
                "credential_type_id": credential_type["id"],
                "project_id": project_id,
                "inputs": {"token": token},
            },
        )
    response.raise_for_status()
    return response.json()["id"]


def _upsert_integration(
    client: httpx.Client, *, endpoint: str, credential_id: str, target_id: UUID
) -> str:
    name = "dev-openshift-cluster"
    configuration = {
        "integration_type": "openshift",
        "base_url": endpoint,
        "namespace": "ep-dev-workers",
        "execution_target_id": str(target_id),
    }
    existing = _by_name(_resources(client, "/api/v1/integrations"), name)
    if existing is not None:
        if existing["integration_type"] != "openshift":
            raise RuntimeError("An integration named dev-openshift-cluster already has another type")
        response = client.patch(
            f"/api/v1/integrations/{existing['id']}",
            json={"configuration": configuration, "management_credential_id": credential_id, "enabled": True},
        )
    else:
        response = client.post(
            "/api/v1/integrations",
            json={
                "name": name,
                "description": "ROSA cold-start worker namespace for development HTTP and Script nodes",
                "integration_type": "openshift",
                "configuration": configuration,
                "management_credential_id": credential_id,
                "scope": "global",
                "enabled": True,
            },
        )
    response.raise_for_status()
    return response.json()["id"]


def main() -> None:
    """Register and validate the development integration without printing secrets."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-url", default="https://localhost:8000")
    parser.add_argument("--endpoint", required=True, help="OpenShift Kubernetes API URL")
    parser.add_argument("--project-name", default="default", help="Syntara credential-owning project")
    parser.add_argument("--target-id", type=UUID, default=UUID("18030000-0000-4000-8000-000000000001"))
    parser.add_argument("--admin-password-file", type=Path, default=Path(".secrets/admin-password"))
    parser.add_argument(
        "--service-account-token-file", type=Path, default=Path(".secrets/execution-plane/openshift-token")
    )
    parser.add_argument("--insecure-local-api-tls", action="store_true")
    args = parser.parse_args()
    if args.insecure_local_api_tls and not args.api_url.startswith(("https://localhost:", "https://127.0.0.1:")):
        raise ValueError("--insecure-local-api-tls is limited to a localhost API")

    password = args.admin_password_file.read_text().strip()
    token = args.service_account_token_file.read_text().strip()
    with httpx.Client(base_url=args.api_url, verify=not args.insecure_local_api_tls, timeout=30) as client:
        login = client.post("/api/v1/auth/login", json={"username": "admin", "password": password})
        login.raise_for_status()
        client.headers["Authorization"] = f"Bearer {login.json()['access_token']}"
        project = _by_name(_resources(client, "/api/v1/projects"), args.project_name)
        if project is None:
            raise RuntimeError(f"Syntara project '{args.project_name}' was not found")
        credential_id = _upsert_credential(client, project["id"], token)
        integration_id = _upsert_integration(
            client, endpoint=args.endpoint, credential_id=credential_id, target_id=args.target_id
        )
        validation = client.post(f"/api/v1/integrations/{integration_id}/validate")
        validation.raise_for_status()
        result = validation.json()
        print(f"Integration ID: {integration_id}")
        print(f"Connection status: {'available' if result.get('success') else 'error'}")
        if not result.get("success"):
            print(f"Validation error: {result.get('error', 'unknown')}")
        print(f"Syntara UI: http://localhost:8080/configuration/integrations/{integration_id}")


if __name__ == "__main__":
    main()
