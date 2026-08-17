#!/usr/bin/env -S uv run
r"""CLI tool for managing authorization data (users, groups, roles, policies, projects).

## Purpose

Development utility for populating and querying authorization data via the Syntara API.
Supports seeding built-in policies/roles, creating entities, and testing access checks.

The ``--username`` flag authenticates as a specific user. Requires ``--password`` (or the
``SYNTARA_CLI_PASSWORD`` env var). When ``--username`` is omitted, the tool authenticates as
``admin`` using the password file at ``APP_ADMIN_PASSWORD_PATH``.

## Usage

    # Seed built-in policies and roles (DB-direct, no auth needed)
    uv run tools/authz_cli.py seed-builtin

    # Clean all non-system data (DB-direct)
    uv run tools/authz_cli.py clean

    # Create entities (as admin by default)
    uv run tools/authz_cli.py create-user alice --email alice@test.com --full-name "Alice" --password secret
    uv run tools/authz_cli.py create-group platform-team

    # Create a project as a specific user
    uv run tools/authz_cli.py --username alice --password secret create-project staging --description "Staging env"

    # Assign roles
    uv run tools/authz_cli.py assign-role user --user alice
    uv run tools/authz_cli.py assign-role user --group platform-team
    uv run tools/authz_cli.py assign-role user --group dev-team --project alpha
    uv run tools/authz_cli.py assign-role project-admin --user bob --project beta

    # Group membership
    uv run tools/authz_cli.py add-group-member platform-team alice

    # List entities
    uv run tools/authz_cli.py list-users
    uv run tools/authz_cli.py list-roles
    uv run tools/authz_cli.py list-policies
    uv run tools/authz_cli.py --username alice --password secret list-projects
    uv run tools/authz_cli.py list-groups

    # View effective permissions (as a specific user)
    uv run tools/authz_cli.py --username alice --password secret what-can-i

    # Check access (uses the in-process authz evaluator)
    uv run tools/authz_cli.py --username alice --password secret can-i read workflow wf-1

    # Machine-readable JSON output for scripting
    uv run tools/authz_cli.py --json --username alice --password secret list-projects
"""
# pragma: no cover - Manual utility, excluded from coverage

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

# Ensure project root is on sys.path
sys.path.insert(0, "src")


def parse_labels(label_strings: list[str] | None) -> dict[str, str]:
    """Parse key=value label strings into a dict."""
    if not label_strings:
        return {}
    labels: dict[str, str] = {}
    for item in label_strings:
        if "=" not in item:
            print(f"Invalid label format: {item} (expected key=value)")
            sys.exit(1)
        key, value = item.split("=", 1)
        labels[key] = value
    return labels


# Module-level config (set by main() from CLI flags)
_DEFAULT_PORT = os.environ.get("APP_API_PORT", "8000")
_DEFAULT_BASE_URL = f"http://localhost:{_DEFAULT_PORT}/api/v1"
_config: dict[str, object] = {
    "base_url": _DEFAULT_BASE_URL,
    "json_mode": False,
    "act_as": None,  # username from --username (None = admin)
    "password": None,  # password from --password or env
    "auth_token": None,
}


async def _ensure_auth_token() -> str | None:
    """Login as the configured user and cache the JWT token."""
    if _config["auth_token"]:
        return str(_config["auth_token"])

    import httpx

    username = str(_config["act_as"]) if _config["act_as"] else "admin"
    password = str(_config["password"]) if _config["password"] else None

    # For admin, fall back to password file
    if username == "admin" and not password:
        pw_path = os.environ.get("APP_ADMIN_PASSWORD_PATH", ".secrets/admin-password")
        try:
            password = Path(pw_path).read_text().strip()
        except FileNotFoundError:
            print(f"Error: admin password file not found at {pw_path}")
            return None

    if not password:
        print(f"Error: --password is required when using --as {username}")
        sys.exit(1)

    url = f"{_config['base_url']}/auth/login"
    async with httpx.AsyncClient() as client:
        resp = await client.post(url, json={"username": username, "password": password})

    if resp.status_code != 200:  # noqa: PLR2004
        print(f"Error: login as '{username}' failed ({resp.status_code}): {resp.text}")
        sys.exit(1)

    token = resp.json().get("access_token")
    _config["auth_token"] = token
    return str(token)


DB_DIRECT_NOTE = "(direct DB — no API endpoint)"


def _build_curl(method: str, path: str, *, body: dict | None = None) -> str:
    """Build a curl command string for display."""
    parts = [f"curl -s -X {method} {_config['base_url']}{path}"]
    if body:
        parts.append('  -H "Content-Type: application/json"')
        parts.append(f"  -d '{json.dumps(body)}'")
    separator = " \\\n  "
    return separator.join(parts)


async def api_request(
    method: str,
    path: str,
    *,
    body: dict | None = None,
) -> tuple[dict | list | None, int]:
    """Make an authenticated HTTP request to the Syntara API. Returns (data, status_code)."""
    import httpx

    if not _config["json_mode"]:
        print(f"\n  {_build_curl(method, path, body=body)}\n")

    headers: dict[str, str] = {}
    token = await _ensure_auth_token()
    if token:
        headers["Authorization"] = f"Bearer {token}"

    url = f"{_config['base_url']}{path}"
    async with httpx.AsyncClient() as client:
        response = await client.request(method, url, headers=headers, json=body)

    status = response.status_code

    if status >= 400:  # noqa: PLR2004
        if _config["json_mode"]:
            print(json.dumps({"status": status, "data": None, "error": response.text}))
        else:
            print(f"  Error {status}: {response.text}")
        return None, status

    if status == 204:  # noqa: PLR2004
        if _config["json_mode"]:
            print(json.dumps({"status": 204, "data": None}))
        else:
            print("  (204 No Content)")
        return None, 204

    data = response.json()
    if _config["json_mode"]:
        print(json.dumps({"status": status, "data": data}))
    else:
        print(f"  ({status})")
    return data, status


async def _resolve_project_id(name: str) -> str | None:
    """Look up a project ID by name via API."""
    data, status = await api_request("GET", "/projects")
    if status >= 400 or data is None:  # noqa: PLR2004
        print(f"Project '{name}' not found")
        return None
    projects = data if isinstance(data, list) else data.get("resources", [])
    match = next((p for p in projects if p.get("name") == name), None)
    if not match:
        print(f"Project '{name}' not found")
        return None
    return str(match["id"])


async def _resolve_user_id(username: str) -> str | None:
    """Look up a user ID by username via API."""
    data, status = await api_request("GET", f"/users?username={username}")
    if status >= 400 or data is None:  # noqa: PLR2004
        print(f"User '{username}' not found")
        return None
    resources = data.get("resources", []) if isinstance(data, dict) else data
    match = next((u for u in resources if u.get("username") == username), None)
    if not match:
        print(f"User '{username}' not found")
        return None
    return str(match["id"])


async def _resolve_group_id(name: str) -> str | None:
    """Look up a group ID by name via API."""
    data, status = await api_request("GET", f"/groups?name={name}")
    if status >= 400 or data is None:  # noqa: PLR2004
        print(f"Group '{name}' not found")
        return None
    resources = data.get("resources", []) if isinstance(data, dict) else data
    match = next((g for g in resources if g.get("name") == name), None)
    if not match:
        print(f"Group '{name}' not found")
        return None
    return str(match["id"])


async def cmd_seed_builtin(args: argparse.Namespace) -> None:
    """Seed built-in policies, roles, groups, default project, and bootstrap admin user."""
    print(DB_DIRECT_NOTE)
    from syntara.authz.seed import seed_authz_data
    from syntara.core.database.session import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        await seed_authz_data(db)
    print("Seed complete (policies, roles, groups, default project, admin user).")


async def cmd_create_user(args: argparse.Namespace) -> None:
    """Create a new user via API."""
    body: dict = {
        "username": args.new_username,
        "email": args.email,
        "full_name": args.full_name,
        "password": args.new_password,
    }

    result, _ = await api_request("POST", "/users", body=body)
    if result and not _config["json_mode"]:
        print(f"Created user: {result['username']} (id={result['id']})")


async def cmd_create_project(args: argparse.Namespace) -> None:
    """Create a new project via API."""
    body: dict = {"name": args.name}
    if args.description:
        body["description"] = args.description
    labels = parse_labels(args.labels)
    if labels:
        body["labels"] = labels

    result, _ = await api_request("POST", "/projects", body=body)
    if result and not _config["json_mode"]:
        print(f"Created project: {result['name']} (id={result['id']})")


async def cmd_delete_project(args: argparse.Namespace) -> None:
    """Delete a project via API."""
    project_id = await _resolve_project_id(args.name)
    if not project_id:
        return
    _, status = await api_request("DELETE", f"/projects/{project_id}")
    if status < 400 and not _config["json_mode"]:  # noqa: PLR2004
        print(f"Deleted project: {args.name}")


async def cmd_create_group(args: argparse.Namespace) -> None:
    """Create a new group via API."""
    body: dict = {"name": args.name}
    if args.description:
        body["description"] = args.description

    result, _ = await api_request("POST", "/groups", body=body)
    if result and not _config["json_mode"]:
        print(f"Created group: {result['name']} (id={result['id']})")


async def cmd_add_group_member(args: argparse.Namespace) -> None:
    """Add a user to a group via API."""
    group_id = await _resolve_group_id(args.group_name)
    if not group_id:
        return
    user_id = await _resolve_user_id(args.member_username)
    if not user_id:
        return

    _, status = await api_request("POST", f"/groups/{group_id}/members", body={"user_id": user_id})
    if status < 400 and not _config["json_mode"]:  # noqa: PLR2004
        print(f"Added {args.member_username} to group {args.group_name}")


async def cmd_create_role(args: argparse.Namespace) -> None:
    """Create a custom role via API."""
    policies = [p.strip() for p in args.policies.split(",")]
    body: dict = {"name": args.name, "policies": policies}
    if args.description:
        body["description"] = args.description

    result, _ = await api_request("POST", "/roles", body=body)
    if result and not _config["json_mode"]:
        print(f"Created role: {result['name']} (id={result['id']}, policies={result['policies']})")


async def cmd_create_policy(args: argparse.Namespace) -> None:
    """Create a custom policy via API."""
    statements = json.loads(args.statements)
    if isinstance(statements, dict):
        statements = [statements]

    body: dict = {"name": args.name, "statements": statements}
    if args.description:
        body["description"] = args.description

    result, _ = await api_request("POST", "/policies", body=body)
    if result and not _config["json_mode"]:
        print(f"Created policy: {result['name']} (id={result['id']})")


async def _assign_project_user_role(role_name: str, target_user: str, project_name: str) -> None:
    """Assign a role to a user in a project via API."""
    project_id = await _resolve_project_id(project_name)
    if not project_id:
        return
    user_id = await _resolve_user_id(target_user)
    if not user_id:
        return
    result, _ = await api_request(
        "POST",
        f"/projects/{project_id}/role-assignments",
        body={"principal_type": "user", "principal_id": user_id, "role_name": role_name},
    )
    if result and not _config["json_mode"]:
        print(f"Assigned role '{role_name}' to user '{target_user}' in project '{project_name}'")


async def _assign_project_group_role(role_name: str, group_name: str, project_name: str) -> None:
    """Assign a role to a group in a project via API."""
    project_id = await _resolve_project_id(project_name)
    if not project_id:
        return
    group_id = await _resolve_group_id(group_name)
    if not group_id:
        return
    result, _ = await api_request(
        "POST",
        f"/projects/{project_id}/role-assignments",
        body={"principal_type": "group", "principal_id": group_id, "role_name": role_name},
    )
    if result and not _config["json_mode"]:
        print(f"Assigned role '{role_name}' to group '{group_name}' in project '{project_name}'")


async def _assign_system_group_role(role_name: str, group_name: str) -> None:
    """Assign a role to a group at system level via API."""
    group_id = await _resolve_group_id(group_name)
    if not group_id:
        return
    result, _ = await api_request(
        "POST",
        "/role-assignments",
        body={"principal_type": "group", "principal_id": group_id, "role_name": role_name},
    )
    if result and not _config["json_mode"]:
        print(f"Assigned role '{role_name}' to group '{group_name}'")


async def _assign_user_role(role_name: str, target_user: str) -> None:
    """Assign a role directly to a user at system level via API."""
    user_id = await _resolve_user_id(target_user)
    if not user_id:
        return
    result, _ = await api_request(
        "POST",
        "/role-assignments",
        body={"principal_type": "user", "principal_id": user_id, "role_name": role_name},
    )
    if result and not _config["json_mode"]:
        print(f"Assigned role '{role_name}' to user '{target_user}'")


async def cmd_assign_role(args: argparse.Namespace) -> None:
    """Assign a role. Supports system and project-scoped assignments for users and groups.

    Modes:
      assign-role <role> --user <user>                        system user→role
      assign-role <role> --group <group>                      system group→role
      assign-role <role> --user <user> --project <proj>       project user→role
      assign-role <role> --group <group> --project <proj>     project group→role
    """
    target_user = getattr(args, "target_user", None)
    project_name = getattr(args, "project", None)
    group_name = getattr(args, "group_name", None)

    if not target_user and not group_name:
        print("Error: must specify --user or --group")
        sys.exit(1)

    if target_user and group_name:
        print("Error: cannot specify both --user and --group")
        sys.exit(1)

    if target_user and project_name:
        await _assign_project_user_role(args.role_name, target_user, project_name)
    elif group_name and project_name:
        await _assign_project_group_role(args.role_name, group_name, project_name)
    elif target_user:
        await _assign_user_role(args.role_name, target_user)
    else:
        await _assign_system_group_role(args.role_name, group_name)


async def cmd_list_users(args: argparse.Namespace) -> None:
    """List all users via API."""
    result, _ = await api_request("GET", "/users")
    if result is None or _config["json_mode"]:
        return

    users = result.get("resources", []) if isinstance(result, dict) else result
    if not users:
        print("No users found.")
        return
    print(f"{'USERNAME':<20} {'EMAIL':<30} {'ACTIVE'}")
    print("-" * 60)
    for u in users:
        print(f"{u['username']:<20} {u['email']:<30} {u.get('is_active', True)}")


async def cmd_list_roles(args: argparse.Namespace) -> None:
    """List all roles via API."""
    result, _ = await api_request("GET", "/roles")
    if result is None or _config["json_mode"]:
        return

    roles = result.get("resources", []) if isinstance(result, dict) else result
    if not roles:
        print("No roles found.")
        return
    print(f"{'NAME':<20} {'BUILTIN':<10} {'POLICIES'}")
    print("-" * 80)
    for r in roles:
        policies_str = ", ".join(r.get("policies", [])) or "[]"
        print(f"{r['name']:<20} {r.get('is_builtin', False)!s:<10} {policies_str}")


async def cmd_list_policies(args: argparse.Namespace) -> None:
    """List all policies via API."""
    result, _ = await api_request("GET", "/policies")
    if result is None or _config["json_mode"]:
        return

    policies = result.get("resources", []) if isinstance(result, dict) else result
    if not policies:
        print("No policies found.")
        return
    print(f"{'NAME':<30} {'BUILTIN':<10} {'STATEMENTS'}")
    print("-" * 80)
    for p in policies:
        stmts_summary = "; ".join(
            f"{s.get('effect', '?')} {','.join(s.get('actions', []))} scope={s.get('scope', '?')}"
            for s in (p.get("statements") or [])
        )
        print(f"{p['name']:<30} {p.get('is_builtin', False)!s:<10} {stmts_summary}")


async def cmd_list_projects(args: argparse.Namespace) -> None:
    """List projects via API (returns only projects visible to the authenticated user)."""
    result, _ = await api_request("GET", "/projects")
    if result is None or _config["json_mode"]:
        return

    projects = result if isinstance(result, list) else result.get("resources", [])
    if not projects:
        print("No projects found.")
        return

    print(f"{'NAME':<20} {'DEFAULT':<10} {'DESCRIPTION'}")
    print("-" * 60)
    for p in projects:
        name = p.get("name", "?")
        is_default = str(p.get("is_default", False))
        desc = p.get("description", "") or ""
        print(f"{name:<20} {is_default:<10} {desc}")


async def cmd_list_groups(args: argparse.Namespace) -> None:
    """List all groups via API."""
    result, _ = await api_request("GET", "/groups")
    if result is None or _config["json_mode"]:
        return

    groups = result.get("resources", []) if isinstance(result, dict) else result
    if not groups:
        print("No groups found.")
        return
    print(f"{'NAME':<20} {'BUILTIN':<10} {'DESCRIPTION'}")
    print("-" * 60)
    for g in groups:
        print(f"{g['name']:<20} {g.get('is_builtin', False)!s:<10} {g.get('description', '') or ''}")


async def cmd_what_can_i(args: argparse.Namespace) -> None:
    """Show all effective permissions for the authenticated user."""
    result, _ = await api_request("POST", "/authz/what-can-i")
    if not result or _config["json_mode"]:
        return

    permissions = result.get("permissions", [])
    username = _config["act_as"] or "admin"
    if not permissions:
        print(f"User '{username}' has no effective permissions.")
        return

    print(f"Effective permissions for '{username}':")
    print(f"  {'SCOPE':<30} {'EFFECT':<8} {'ACTIONS'}")
    print("  " + "-" * 70)
    for p in permissions:
        scope = p.get("scope", "?")
        project = p.get("project", "")
        scope_str = f"{scope} ({project})" if project else scope
        effect = p.get("effect", "?")
        actions = p.get("actions", [])
        print(f"  {scope_str:<30} {effect:<8} {actions}")


async def cmd_remove_group_member(args: argparse.Namespace) -> None:
    """Remove a user from a group via API."""
    group_id = await _resolve_group_id(args.group_name)
    if not group_id:
        return
    user_id = await _resolve_user_id(args.member_username)
    if not user_id:
        return

    _, status = await api_request("DELETE", f"/groups/{group_id}/members/{user_id}")
    if status < 400 and not _config["json_mode"]:  # noqa: PLR2004
        print(f"Removed {args.member_username} from group {args.group_name}")


async def _unassign_project_user_role(role_name: str, target_user: str, project_name: str) -> None:
    """Remove a user's role in a project via API."""
    project_id = await _resolve_project_id(project_name)
    if not project_id:
        return
    user_id = await _resolve_user_id(target_user)
    if not user_id:
        return
    response, _ = await api_request(
        "GET",
        f"/projects/{project_id}/role-assignments?principal_type=user&principal_id={user_id}&role_name={role_name}",
    )
    assignments = response.get("resources", []) if response else []
    if not assignments:
        if not _config["json_mode"]:
            print(f"Role '{role_name}' is not assigned to user '{target_user}' in project '{project_name}'")
        return
    await api_request("DELETE", f"/projects/{project_id}/role-assignments/{assignments[0]['id']}")
    if not _config["json_mode"]:
        print(f"Removed role '{role_name}' from user '{target_user}' in project '{project_name}'")


async def _unassign_project_group_role(role_name: str, group_name: str, project_name: str) -> None:
    """Remove a group's role in a project via API."""
    project_id = await _resolve_project_id(project_name)
    if not project_id:
        return
    group_id = await _resolve_group_id(group_name)
    if not group_id:
        return
    response, _ = await api_request(
        "GET",
        f"/projects/{project_id}/role-assignments?principal_type=group&principal_id={group_id}&role_name={role_name}",
    )
    assignments = response.get("resources", []) if response else []
    if not assignments:
        if not _config["json_mode"]:
            print(f"Role '{role_name}' is not assigned to group '{group_name}' in project '{project_name}'")
        return
    await api_request("DELETE", f"/projects/{project_id}/role-assignments/{assignments[0]['id']}")
    if not _config["json_mode"]:
        print(f"Removed role '{role_name}' from group '{group_name}' in project '{project_name}'")


async def _unassign_system_group_role(role_name: str, group_name: str) -> None:
    """Remove a group's system-level role via API."""
    response, _ = await api_request(
        "GET", f"/role-assignments?principal_type=group&principal_name={group_name}&role_name={role_name}"
    )
    assignments = response.get("resources", []) if response else []
    if not assignments:
        if not _config["json_mode"]:
            print(f"Role '{role_name}' is not assigned to group '{group_name}'")
        return
    await api_request("DELETE", f"/role-assignments/{assignments[0]['id']}")
    if not _config["json_mode"]:
        print(f"Removed role '{role_name}' from group '{group_name}'")


async def _unassign_user_role(role_name: str, target_user: str) -> None:
    """Remove a direct user→role assignment at system level via API."""
    response, _ = await api_request(
        "GET", f"/role-assignments?principal_type=user&principal_name={target_user}&role_name={role_name}"
    )
    assignments = response.get("resources", []) if response else []
    if not assignments:
        if not _config["json_mode"]:
            print(f"Role '{role_name}' is not assigned to user '{target_user}'")
        return
    await api_request("DELETE", f"/role-assignments/{assignments[0]['id']}")
    if not _config["json_mode"]:
        print(f"Removed role '{role_name}' from user '{target_user}'")


async def cmd_unassign_role(args: argparse.Namespace) -> None:
    """Remove a role assignment. Supports system and project-scoped for users and groups."""
    target_user = getattr(args, "target_user", None)
    project_name = getattr(args, "project", None)
    group_name = getattr(args, "group_name", None)

    if not target_user and not group_name:
        print("Error: must specify --user or --group")
        sys.exit(1)

    if target_user and group_name:
        print("Error: cannot specify both --user and --group")
        sys.exit(1)

    if target_user and project_name:
        await _unassign_project_user_role(args.role_name, target_user, project_name)
    elif group_name and project_name:
        await _unassign_project_group_role(args.role_name, group_name, project_name)
    elif target_user:
        await _unassign_user_role(args.role_name, target_user)
    else:
        await _unassign_system_group_role(args.role_name, group_name)


async def cmd_clean(args: argparse.Namespace) -> None:
    """Remove all non-system data using raw SQL to avoid ORM cascade issues.

    After clean, run ``seed-builtin`` to restore builtin role assignments.
    """
    print(DB_DIRECT_NOTE)

    if not getattr(args, "yes", False):
        confirm = input("This will delete all non-system data. Continue? [y/N] ")
        if confirm.lower() != "y":
            print("Aborted.")
            return

    from sqlmodel import text

    from syntara.core.database.session import AsyncSessionLocal

    # Tables to clean in FK-safe order, with conditions to preserve system data
    clean_steps = [
        ("approval_requests", None),
        ("activity_execution", None),
        ("executions", None),
        ("workflow_versions", None),
        ("workflows", None),
        ("credentials", None),
        ("credential_types", "managed = false"),
        ("role_assignments", None),
        ("user_groups", "group_id IN (SELECT id FROM groups WHERE is_builtin = false)"),
        ("roles", "is_builtin = false"),
        ("policies", "is_builtin = false"),
        ("projects", "is_default = false"),
        ("users", "username != 'admin'"),
        ("groups", "is_builtin = false"),
    ]

    async with AsyncSessionLocal() as db:
        # Clear deleted_by on default project first (FK to users)
        await db.exec(text("UPDATE projects SET deleted_by = NULL, deleted_at = NULL WHERE is_default = true"))

        for table, condition in clean_steps:
            sql = f"DELETE FROM {table}"  # noqa: S608
            if condition:
                sql += f" WHERE {condition}"
            result = await db.exec(text(sql))
            print(f"  {table}: {result.rowcount} row(s) deleted")  # type: ignore[union-attr]

        await db.commit()
    print("Clean complete. Run 'seed-builtin' to restore builtin role assignments.")


def _sample_workflow_definition(name: str, description: str) -> dict:
    """Build a minimal V2 workflow definition."""
    return {
        "schema_version": "2.0.0",
        "name": name,
        "description": description,
        "triggers": [{"id": "trigger_manual", "type": "manual_trigger"}],
        "nodes": [
            {
                "id": "step1",
                "type": "script",
                "name": f"Run {name}",
                "config": {
                    "language": "python",
                    "code": f"print('Running {name}')",
                    "timeout": 300,
                },
            }
        ],
        "edges": [{"from": "trigger_manual", "to": "step1"}],
    }


async def cmd_create_sample_workflow(args: argparse.Namespace) -> None:
    """Create one or more simple runnable workflows, optionally in a project."""
    project_name = getattr(args, "project", None)
    base_name = getattr(args, "name", None) or "sample-wf"
    count = getattr(args, "count", 1) or 1

    project_id = None
    if project_name:
        project_id = await _resolve_project_id(project_name)
        if not project_id:
            return

    for i in range(count):
        name = base_name if count == 1 else f"{base_name}-{i + 1}"
        desc = f"Sample workflow: {name}"
        body: dict = {
            "name": name,
            "description": desc,
            "workflow_definition": _sample_workflow_definition(name, desc),
        }
        if project_id:
            body["project_id"] = project_id

        result, _ = await api_request("POST", "/workflows", body=body)
        if result and not _config["json_mode"]:
            print(f"Created workflow: {result['name']} (id={result['id']})")


async def cmd_list_workflows(args: argparse.Namespace) -> None:
    """List workflows via API, optionally filtered by project."""
    project_name = getattr(args, "project", None)

    result, _ = await api_request("GET", "/workflows?limit=100")
    if result is None or _config["json_mode"]:
        return

    workflows = result.get("resources", []) if isinstance(result, dict) else result

    # Filter by project if specified
    if project_name:
        project_id = await _resolve_project_id(project_name)
        if project_id:
            workflows = [w for w in workflows if w.get("project_id") == project_id]

    if not workflows:
        print("No workflows found.")
        return

    # Build project name map for display
    project_map = await _build_project_name_map()

    print(f"{'NAME':<30} {'PROJECT':<20} {'ENABLED'}")
    print("-" * 58)
    for w in workflows:
        proj = project_map.get(w.get("project_id", ""), "(none)")
        print(f"{w['name']:<30} {proj:<20} {w.get('is_enabled', True)}")


async def cmd_run_workflow(args: argparse.Namespace) -> None:
    """Execute a workflow by name via API."""
    # Resolve workflow name to ID
    result, _ = await api_request("GET", "/workflows?limit=100")
    if not result:
        return

    workflows = result.get("resources", []) if isinstance(result, dict) else result
    match = next((w for w in workflows if w.get("name") == args.workflow_name), None)
    if not match:
        print(f"Workflow '{args.workflow_name}' not found")
        return

    workflow_id = match["id"]
    body: dict = {"workflow_id": workflow_id, "input_data": {}}

    exec_result, _ = await api_request("POST", "/executions", body=body)
    if exec_result and not _config["json_mode"]:
        print(
            f"Started execution: {exec_result['id']} "
            f"(workflow={args.workflow_name}, status={exec_result.get('status', '?')})"
        )


async def _build_project_name_map() -> dict[str, str]:
    """Build a project_id -> project_name lookup map."""
    result, _ = await api_request("GET", "/projects")
    if not result:
        return {}
    projects = result if isinstance(result, list) else result.get("resources", [])
    return {p["id"]: p["name"] for p in projects}


async def cmd_list_executions(args: argparse.Namespace) -> None:
    """List executions via API, optionally filtered by project."""
    project_name = getattr(args, "project", None)

    result, _ = await api_request("GET", "/executions")
    if result is None or _config["json_mode"]:
        return

    executions = result.get("resources", []) if isinstance(result, dict) else result

    # Filter by project if specified
    if project_name:
        project_id = await _resolve_project_id(project_name)
        if project_id:
            executions = [e for e in executions if e.get("project_id") == project_id]

    if not executions:
        print("No executions found.")
        return

    # Build project name map for display
    project_map = await _build_project_name_map()

    print(f"{'ID':<38} {'WORKFLOW_ID':<38} {'PROJECT':<20} {'STATUS':<12}")
    print("-" * 108)
    for e in executions:
        proj = project_map.get(e.get("project_id", ""), "(none)")
        print(f"{e['id']:<38} {e['workflow_id']:<38} {proj:<20} {e.get('status', '?'):<12}")


async def cmd_who_can(args: argparse.Namespace) -> None:
    """Check which users can perform an action via API."""
    body: dict = {"action": args.action, "resource_type": args.resource_type}
    if args.resource_id:
        body["resource_id"] = args.resource_id
    resource_labels = parse_labels(getattr(args, "resource_labels", None))
    if resource_labels:
        body["resource_labels"] = resource_labels

    result, _ = await api_request("POST", "/authz/who-can", body=body)
    if not result or _config["json_mode"]:
        return

    users = result.get("users", [])
    if not users:
        print(f"No users can perform {args.action} on {args.resource_type}")
        return

    print(f"Users who can {args.action} {args.resource_type}:")
    for u in users:
        print(f"  {u['username']} (id={u['id']})")


async def cmd_can_i(args: argparse.Namespace) -> None:
    """Check if the authenticated user can perform an action via API."""
    body: dict = {"action": args.action, "resource_type": args.resource_type, "resource_id": args.resource_id}
    resource_labels = parse_labels(getattr(args, "resource_labels", None))
    if resource_labels:
        body["resource_labels"] = resource_labels
    resource_project = getattr(args, "resource_project", None)
    if resource_project:
        body["resource_project"] = resource_project
    resource_metadata = getattr(args, "resource_metadata", None)
    if resource_metadata:
        body["resource_metadata"] = json.loads(resource_metadata)
    result, _ = await api_request("POST", "/authz/can-i", body=body)
    if not result or _config["json_mode"]:
        return

    username = _config["act_as"] or "admin"
    print(f"User:     {username}")
    print(f"Action:   {args.resource_type}:{args.action}")
    print(f"Resource: {args.resource_id}")
    print(f"Allowed:  {result.get('allowed', False)}")
    if result.get("matched_policy"):
        print(f"Matched:  {result['matched_policy']}")
    if result.get("denied"):
        print(f"Denied:   {result.get('denied_by', '')} ({result.get('denial_reason', '')})")


def _register_entity_commands(sub: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    """Register entity management subcommands."""
    sub.add_parser("seed-builtin", help="Seed built-in policies and roles")
    p = sub.add_parser("clean", help="Remove all non-system data (run seed-builtin after)")
    p.add_argument("-y", "--yes", action="store_true", help="Skip confirmation prompt")

    p = sub.add_parser("create-user", help="Create a new user")
    p.add_argument("new_username", metavar="username")
    p.add_argument("--email", required=True)
    p.add_argument("--full-name", required=True)
    p.add_argument("--password", dest="new_password", required=True, help="Password for the new user")

    p = sub.add_parser("create-project", help="Create a new project")
    p.add_argument("name")
    p.add_argument("--description", default=None)
    p.add_argument("--labels", nargs="*", help="Labels as key=value pairs")

    p = sub.add_parser("delete-project", help="Delete a project")
    p.add_argument("name")

    p = sub.add_parser("create-sample-workflow", help="Create simple runnable workflow(s)")
    p.add_argument("--name", default="sample-wf", help="Workflow name (default: sample-wf)")
    p.add_argument("--project", default=None, help="Project to assign workflow to")
    p.add_argument("--count", type=int, default=1, help="Number of workflows to create (default: 1)")

    p = sub.add_parser("create-group", help="Create a new group")
    p.add_argument("name")
    p.add_argument("--description", default=None)

    p = sub.add_parser("add-group-member", help="Add a user to a group")
    p.add_argument("group_name")
    p.add_argument("member_username", metavar="username")

    p = sub.add_parser("remove-group-member", help="Remove a user from a group")
    p.add_argument("group_name")
    p.add_argument("member_username", metavar="username")


def _register_role_commands(sub: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    """Register role/policy management subcommands."""
    p = sub.add_parser("create-role", help="Create a custom role")
    p.add_argument("name")
    p.add_argument("--policies", required=True, help="Comma-separated policy names")
    p.add_argument("--description", default=None)

    p = sub.add_parser("create-policy", help="Create a custom policy")
    p.add_argument("name")
    p.add_argument("--statements", required=True, help="JSON array of statements")
    p.add_argument("--description", default=None)

    p = sub.add_parser("assign-role", help="Assign a role to a user or group")
    p.add_argument("role_name")
    p.add_argument("--user", dest="target_user", default=None, help="Target user")
    p.add_argument("--group", dest="group_name", default=None, help="Target group")
    p.add_argument("--project", default=None, help="Project scope")

    p = sub.add_parser("unassign-role", help="Remove a role from a user or group")
    p.add_argument("role_name")
    p.add_argument("--user", dest="target_user", default=None, help="Target user")
    p.add_argument("--group", dest="group_name", default=None, help="Target group")
    p.add_argument("--project", default=None, help="Project scope")


def _register_query_commands(sub: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    """Register list/query subcommands."""
    sub.add_parser("list-users", help="List all users")
    sub.add_parser("list-roles", help="List all roles")
    sub.add_parser("list-policies", help="List all policies")
    sub.add_parser("list-projects", help="List projects visible to authenticated user")
    sub.add_parser("list-groups", help="List all groups")

    p = sub.add_parser("list-workflows", help="List workflows visible to authenticated user")
    p.add_argument("--project", default=None, help="Filter by project name")

    p = sub.add_parser("run-workflow", help="Execute a workflow by name")
    p.add_argument("workflow_name")

    p = sub.add_parser("list-executions", help="List executions")
    p.add_argument("--project", default=None, help="Filter by project name")

    sub.add_parser("what-can-i", help="Show effective permissions for authenticated user")

    p = sub.add_parser("can-i", help="Check if authenticated user can perform an action")
    p.add_argument("action")
    p.add_argument("resource_type")
    p.add_argument("resource_id", nargs="?", default="")
    p.add_argument("--resource-labels", nargs="*", help="Resource labels as key=value pairs")
    p.add_argument("--resource-project", default=None, help="Resource project ID or name")
    p.add_argument("--resource-metadata", default=None, help="Resource metadata as JSON string")

    p = sub.add_parser("who-can", help="List users who can perform an action")
    p.add_argument("action")
    p.add_argument("resource_type")
    p.add_argument("resource_id", nargs="?", default="")
    p.add_argument("--resource-labels", nargs="*", help="Resource labels as key=value pairs")


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(
        description="Authorization CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--base-url", default=_DEFAULT_BASE_URL, help="API base URL")
    parser.add_argument("--json", dest="json_mode", action="store_true", help="Machine-readable JSON output")
    parser.add_argument(
        "--username",
        default=None,
        help="Authenticate as this user (default: admin)",
    )
    parser.add_argument(
        "--password",
        default=os.environ.get("SYNTARA_CLI_PASSWORD"),
        help="Password for --username (default: $SYNTARA_CLI_PASSWORD or admin password file)",
    )
    sub = parser.add_subparsers(dest="command", help="Available commands")
    _register_entity_commands(sub)
    _register_role_commands(sub)
    _register_query_commands(sub)
    return parser


COMMAND_MAP = {
    "seed-builtin": cmd_seed_builtin,
    "clean": cmd_clean,
    "create-user": cmd_create_user,
    "create-project": cmd_create_project,
    "delete-project": cmd_delete_project,
    "create-group": cmd_create_group,
    "add-group-member": cmd_add_group_member,
    "create-sample-workflow": cmd_create_sample_workflow,
    "create-role": cmd_create_role,
    "create-policy": cmd_create_policy,
    "assign-role": cmd_assign_role,
    "list-users": cmd_list_users,
    "list-roles": cmd_list_roles,
    "list-policies": cmd_list_policies,
    "list-projects": cmd_list_projects,
    "list-workflows": cmd_list_workflows,
    "run-workflow": cmd_run_workflow,
    "list-executions": cmd_list_executions,
    "list-groups": cmd_list_groups,
    "what-can-i": cmd_what_can_i,
    "remove-group-member": cmd_remove_group_member,
    "unassign-role": cmd_unassign_role,
    "can-i": cmd_can_i,
    "who-can": cmd_who_can,
}


def main() -> None:
    """CLI entry point."""
    parser = build_parser()
    args = parser.parse_args()

    _config["base_url"] = args.base_url
    _config["json_mode"] = args.json_mode
    _config["act_as"] = args.username
    _config["password"] = args.password

    if not args.command:
        parser.print_help()
        sys.exit(1)

    handler = COMMAND_MAP.get(args.command)
    if not handler:
        print(f"Unknown command: {args.command}")
        sys.exit(1)

    asyncio.run(handler(args))


if __name__ == "__main__":
    main()
