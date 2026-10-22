#!/usr/bin/env python3
"""Create or refresh an AO bearer-token credential for an Execution Plane target."""

from __future__ import annotations

import argparse
import json
import os
import ssl
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from uuid import UUID

DEFAULT_API_URL = "https://127.0.0.1:8443"
DEFAULT_CREDENTIAL_TYPE_NAME = "HTTP Bearer Token"
REQUEST_TIMEOUT_SECONDS = 30.0


def _request_json(
    method: str,
    url: str,
    *,
    payload: dict[str, object] | None = None,
    headers: dict[str, str] | None = None,
    insecure: bool = False,
) -> object:
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = Request(url, data=body, headers=headers or {}, method=method)  # noqa: S310
    if body is not None:
        request.add_header("Content-Type", "application/json")

    context = ssl.create_default_context()
    if insecure:
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE

    try:
        with urlopen(request, context=context, timeout=REQUEST_TIMEOUT_SECONDS) as response:  # noqa: S310
            response_body = response.read()
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        message = f"{method} {url} failed with HTTP {exc.code}: {detail}"
        raise RuntimeError(message) from exc
    except URLError as exc:
        message = f"{method} {url} failed: {exc.reason}"
        raise RuntimeError(message) from exc

    if not response_body:
        return None
    try:
        return json.loads(response_body)
    except json.JSONDecodeError as exc:
        message = f"{method} {url} returned invalid JSON"
        raise RuntimeError(message) from exc


def _resource_list(response: object, endpoint: str) -> list[dict[str, object]]:
    resources = response.get("resources") if isinstance(response, dict) else None
    if not isinstance(resources, list):
        message = f"AO {endpoint} response has no resources list"
        raise TypeError(message)
    return [resource for resource in resources if isinstance(resource, dict)]


def _login(api_url: str, username: str, password: str, *, insecure: bool) -> str:
    response = _request_json(
        "POST",
        f"{api_url.rstrip('/')}/api/v1/auth/login",
        payload={"username": username, "password": password},
        insecure=insecure,
    )
    access_token = response.get("access_token") if isinstance(response, dict) else None
    if not isinstance(access_token, str) or not access_token:
        message = "AO login did not return an access token"
        raise RuntimeError(message)
    return access_token


def _default_project_id(api_url: str, headers: dict[str, str], *, insecure: bool) -> str:
    response = _request_json(
        "GET",
        f"{api_url.rstrip('/')}/api/v1/projects?limit=100",
        headers=headers,
        insecure=insecure,
    )
    projects = _resource_list(response, "projects")
    project = next((item for item in projects if item.get("is_default") is True), None)
    if project is None and projects:
        project = projects[0]
    project_id = project.get("id") if project is not None else None
    if not isinstance(project_id, str) or not project_id:
        message = "AO has no project available for the Execution Plane credential"
        raise RuntimeError(message)
    return project_id


def _bearer_credential_type_id(
    api_url: str,
    headers: dict[str, str],
    credential_type_name: str,
    *,
    insecure: bool,
) -> str:
    response = _request_json(
        "GET",
        f"{api_url.rstrip('/')}/api/v1/credential_types?limit=100",
        headers=headers,
        insecure=insecure,
    )
    credential_types = _resource_list(response, "credential types")
    credential_type = next(
        (item for item in credential_types if item.get("name") == credential_type_name),
        None,
    )
    credential_type_id = credential_type.get("id") if credential_type is not None else None
    if not isinstance(credential_type_id, str) or not credential_type_id:
        message = f"AO credential type {credential_type_name!r} was not found"
        raise RuntimeError(message)
    return credential_type_id


def create_or_refresh_credential(
    *,
    api_url: str,
    cluster_name: str,
    token: str,
    username: str,
    password: str,
    credential_name: str | None = None,
    credential_type_name: str = DEFAULT_CREDENTIAL_TYPE_NAME,
    insecure: bool = False,
) -> UUID:
    """Create the named AO credential or refresh its bearer-token input."""
    api_root = api_url.rstrip("/")
    access_token = _login(api_root, username, password, insecure=insecure)
    headers = {"Authorization": f"Bearer {access_token}"}
    project_id = _default_project_id(api_root, headers, insecure=insecure)
    credential_type_id = _bearer_credential_type_id(
        api_root,
        headers,
        credential_type_name,
        insecure=insecure,
    )
    name = credential_name or f"execution-plane-{cluster_name}"
    query = urlencode({"limit": "100", "name": name})
    response = _request_json(
        "GET",
        f"{api_root}/api/v1/credentials?{query}",
        headers=headers,
        insecure=insecure,
    )
    credentials = _resource_list(response, "credentials")
    existing = next((item for item in credentials if item.get("name") == name), None)

    if existing is None:
        created = _request_json(
            "POST",
            f"{api_root}/api/v1/credentials",
            headers=headers,
            payload={
                "name": name,
                "description": "Execution Plane Kind dispatcher ServiceAccount token",
                "credential_type_id": credential_type_id,
                "inputs": {"token": token},
                "labels": {"execution-plane.syntara.io/cluster": cluster_name},
                "project_id": project_id,
            },
            insecure=insecure,
        )
    else:
        existing_id = existing.get("id")
        if not isinstance(existing_id, str):
            message = f"AO credential {name!r} has no id"
            raise RuntimeError(message)
        created = _request_json(
            "PATCH",
            f"{api_root}/api/v1/credentials/{existing_id}",
            headers=headers,
            payload={"inputs": {"token": token}, "enabled": True},
            insecure=insecure,
        )

    credential_id = created.get("id") if isinstance(created, dict) else None
    if not isinstance(credential_id, str):
        message = "AO credential response has no id"
        raise TypeError(message)
    try:
        return UUID(credential_id)
    except ValueError as exc:
        message = f"AO credential id {credential_id!r} is not a UUID"
        raise RuntimeError(message) from exc


def _read_secret(
    environment_value: str | None,
    file_path: Path | None,
    environment_name: str,
    file_option_name: str,
) -> str:
    if environment_value:
        return environment_value
    if file_path is not None:
        value = file_path.read_text(encoding="utf-8").strip()
        if value:
            return value
    message = f"{environment_name} or {file_option_name} is required"
    raise RuntimeError(message)


def main() -> int:
    """Parse command-line arguments and print the AO credential UUID."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-url", default=os.environ.get("AO_API_BASE", DEFAULT_API_URL))
    parser.add_argument("--cluster-name", required=True)
    parser.add_argument("--credential-name")
    parser.add_argument("--credential-type-name", default=DEFAULT_CREDENTIAL_TYPE_NAME)
    parser.add_argument("--admin-username", default=os.environ.get("ADMIN_USERNAME", "admin"))
    parser.add_argument("--admin-password-file", type=Path)
    parser.add_argument("--token-file", type=Path)
    parser.add_argument("--insecure", action="store_true")
    args = parser.parse_args()

    try:
        admin_password = _read_secret(
            os.environ.get("AO_ADMIN_PASSWORD"),
            args.admin_password_file,
            "AO_ADMIN_PASSWORD",
            "--admin-password-file",
        )
        token = _read_secret(
            os.environ.get("AO_CREDENTIAL_TOKEN"),
            args.token_file,
            "AO_CREDENTIAL_TOKEN",
            "--token-file",
        )
        credential_id = create_or_refresh_credential(
            api_url=args.api_url,
            cluster_name=args.cluster_name,
            token=token,
            username=args.admin_username,
            password=admin_password,
            credential_name=args.credential_name,
            credential_type_name=args.credential_type_name,
            insecure=args.insecure,
        )
    except (OSError, RuntimeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(credential_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
