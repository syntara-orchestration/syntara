#!/usr/bin/env python3
"""Create a project policy denying agentic workflow nodes in the default project.

Uses SYNTARA_TOKEN when set; otherwise logs in as admin using
APP_ADMIN_PASSWORD_PATH or backend/.secrets/admin-password (and prompts if
neither password source is available). Set SYNTARA_API_URL to override the
default http://localhost:8000/api/v1.
"""

import getpass
import json
import os
import sys
from pathlib import Path

import httpx


def api_request(
    base_url: str,
    method: str,
    path: str,
    body: dict | None = None,
    token: str | None = None,
) -> dict:
    """Send an API request and return its JSON response."""
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if data is not None:
        headers["Content-Type"] = "application/json"

    try:
        response = httpx.request(
            method,
            f"{base_url.rstrip('/')}{path}",
            content=data,
            headers=headers,
            timeout=20,
        )
        response.raise_for_status()
        return response.json()
    except httpx.HTTPStatusError as exc:
        raise RuntimeError(f"{method} {path} failed ({exc.response.status_code}): {exc.response.text}") from exc
    except httpx.RequestError as exc:
        raise RuntimeError(f"Could not reach {base_url}: {exc}") from exc


def get_access_token(base_url: str) -> str:
    """Use the configured token or log in as the local admin."""
    token = os.environ.get("SYNTARA_TOKEN")
    if token:
        return token

    username = os.environ.get("SYNTARA_USERNAME", "admin")
    password = os.environ.get("SYNTARA_PASSWORD")
    if not password:
        default_password_path = Path(__file__).resolve().parents[1] / ".secrets" / "admin-password"
        password_path = Path(os.environ.get("APP_ADMIN_PASSWORD_PATH", str(default_password_path)))
        try:
            password = password_path.read_text().strip()
        except FileNotFoundError:
            password = getpass.getpass(f"Password for {username}: ")

    response = api_request(
        base_url,
        "POST",
        "/auth/login",
        {"username": username, "password": password},
    )
    token = response.get("access_token")
    if not token:
        message = "Login response did not include an access token."
        raise RuntimeError(message)
    return token


def main() -> None:
    """Create a project policy denying agentic workflow nodes."""
    base_url = os.environ.get("SYNTARA_API_URL", "http://localhost:8000/api/v1")
    token = get_access_token(base_url)
    response = api_request(base_url, "GET", "/projects?is_default=true&limit=10", token=token)
    projects = response.get("resources", [])
    if len(projects) != 1:
        sys.exit(f"Expected one accessible default project; found {len(projects)}.")

    project_id = projects[0]["id"]
    policy = api_request(
        base_url,
        "POST",
        f"/projects/{project_id}/policies",
        {
            "name": "deny-agentic-node",
            "description": "Deny agentic workflow node execution in the default project.",
            "statements": [
                {
                    "effect": "deny",
                    "actions": ["workflow_node:execute"],
                    "scope": "project",
                    "conditions": {"resource_labels": {"kind": "agentic"}},
                }
            ],
        },
        token,
    )
    print(json.dumps(policy, indent=2))
    print("Assign this policy to the project role(s) whose members should be denied agentic nodes.")


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as exc:
        sys.exit(str(exc))
