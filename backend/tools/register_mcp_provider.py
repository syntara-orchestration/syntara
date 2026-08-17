"""Register an MCP tool provider, validate it, and refresh its tools.

Steps:
  0. Authenticate with the API (login as admin)
  1. Register the MCP provider (or reuse existing one by name)
  2. Validate the provider connection
  3. Refresh the tools list
"""

import os
import sys
from pathlib import Path
from typing import Any

import httpx

BASE_URL = "http://127.0.0.1:8000/api/v1"
PROVIDER_NAME = "mcp"
MCP_BASE_URL = "http://syntara_mcp-server_1:8765/mcp"


def _get_access_token() -> str:
    """Authenticate and return a Bearer access token."""
    password_path = os.environ.get("APP_ADMIN_PASSWORD_PATH", ".secrets/admin-password")
    password = Path(password_path).read_text().strip()
    r = httpx.post(
        f"{BASE_URL}/auth/login",
        json={"username": "admin", "password": password},
    )
    r.raise_for_status()
    return r.json()["access_token"]  # type: ignore[no-any-return]


AUTH_HEADERS = {"Authorization": f"Bearer {_get_access_token()}"}


def _post(path: str, **kwargs: Any) -> dict[str, Any]:
    headers = {**AUTH_HEADERS, **kwargs.pop("headers", {})}
    r = httpx.post(f"{BASE_URL}{path}", headers=headers, **kwargs)
    r.raise_for_status()
    return r.json()  # type: ignore[no-any-return]


def _get(path: str, **kwargs: Any) -> dict[str, Any]:
    headers = {**AUTH_HEADERS, **kwargs.pop("headers", {})}
    r = httpx.get(f"{BASE_URL}{path}", headers=headers, **kwargs)
    r.raise_for_status()
    return r.json()  # type: ignore[no-any-return]


# --- Step 1: Register or find existing provider ---
existing = [
    p
    for p in _get("/tool_manager/tool_providers", params={"name": PROVIDER_NAME})["resources"]
    if p["name"] == PROVIDER_NAME
]

if existing:
    provider_id = existing[0]["id"]
    sys.stdout.write(f"Provider already exists: {provider_id}\n")
else:
    data = _post(
        "/tool_manager/tool_providers",
        json={
            "name": PROVIDER_NAME,
            "description": "Local MCP server",
            "configuration": {
                "provider_type": "mcp",
                "base_url": MCP_BASE_URL,
            },
        },
    )
    provider_id = data["id"]
    sys.stdout.write(f"Registered provider: {provider_id}\n")

# --- Step 2: Validate ---
sys.stdout.write("Validating provider...\n")
result = _post(f"/tool_manager/tool_providers/{provider_id}/validate")
sys.stdout.write(f"  valid={result['valid']}  provider_type={result['provider_type']}\n")
if result.get("error"):
    sys.stderr.write(f"  error: {result['error']}\n")
    sys.exit(1)

# --- Step 3: Refresh tools ---
sys.stdout.write("Refreshing tools...\n")
refresh = _post(f"/tool_manager/tool_providers/{provider_id}/refresh_tools")
sys.stdout.write(
    f"  updated={refresh['updated_count']}  refreshed={refresh['refreshed_count']}  "
    f"disabled={refresh['disabled_count']}\n"
)

# --- Show registered tools ---
tools = _get("/tools", params={"provider_id": provider_id, "limit": 100})["resources"]
sys.stdout.write(f"\nTools ({len(tools)}):\n")
for t in tools:
    sys.stdout.write(f"  {t['namespaced_name']}  status={t['status']}\n")
