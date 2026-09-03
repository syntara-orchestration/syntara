"""Create a pending approval workflow for Laura's Message screenshot. Never prints secrets."""

from __future__ import annotations

import json
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PASSWORD_PATH = ROOT / "backend/.secrets/admin-password"
API = "https://localhost:8000/api/v1"
UI = "http://localhost:5173"
WORKFLOW_NAME = "Laura Approval Screenshot"
APPROVAL_NAME = "Production Deployment Approval"
MESSAGE = (
    "Review the staging test results and approve deployment of v${trigger.version} to ${trigger.environment}."
)

CTX = ssl._create_unverified_context()


def request(method: str, path: str, token: str | None = None, body: dict | None = None) -> tuple[int, dict | list | None]:
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(f"{API}{path}", data=data, method=method)
    req.add_header("Accept", "application/json")
    if body is not None:
        req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, context=CTX, timeout=30) as resp:
            raw = resp.read()
            return resp.status, json.loads(raw) if raw else None
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        parsed = None
        if raw:
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                parsed = {"detail": raw.decode(errors="replace")[:300]}
        return exc.code, parsed


def find_workflow_id(token: str) -> str | None:
    query = urllib.parse.urlencode({"limit": 100})
    status, payload = request("GET", f"/workflows?{query}", token)
    if status != 200 or not isinstance(payload, dict):
        return None
    match = next((row for row in payload.get("resources") or [] if row.get("name") == WORKFLOW_NAME), None)
    return match["id"] if match else None


def main() -> int:
    password = PASSWORD_PATH.read_text().strip()
    status, payload = request("POST", "/auth/login", body={"username": "admin", "password": password})
    del password
    if status != 200 or not isinstance(payload, dict) or not payload.get("access_token"):
        print(f"login_failed status={status}")
        return 1
    token = payload["access_token"]

    status, payload = request("GET", "/projects?limit=20", token)
    if status != 200 or not isinstance(payload, dict):
        print(f"projects_failed status={status}")
        return 1
    projects = payload.get("resources") or []
    if not projects:
        print("no_projects")
        return 1
    project_id = projects[0]["id"]

    definition = {
        "schema_version": "2.0.0",
        "name": WORKFLOW_NAME,
        "triggers": [{"id": "trigger", "type": "manual_trigger", "name": "Manual trigger", "parameters": {}}],
        "nodes": [
            {
                "id": "approval_gate",
                "name": APPROVAL_NAME,
                "type": "approval",
                "parameters": {"prompt": MESSAGE, "approver_users": ["admin"]},
            },
            {
                "id": "post_approval",
                "name": "Deploy to Production",
                "type": "script",
                "parameters": {"language": "python", "code": 'print("approved")'},
            },
        ],
        "edges": [
            {"from": "trigger", "to": "approval_gate"},
            {"from": "approval_gate", "to": "post_approval", "from_port": "approved"},
        ],
    }

    workflow_id = find_workflow_id(token)
    if workflow_id:
        status, payload = request(
            "PATCH",
            f"/workflows/{workflow_id}",
            token,
            {"workflow_definition": definition},
        )
        if status not in {200, 201}:
            print(f"update_workflow_failed status={status} body={payload}")
            return 1
    else:
        status, payload = request(
            "POST",
            "/workflows",
            token,
            {
                "name": WORKFLOW_NAME,
                "description": "Pending approval for Laura Message screenshot (AAP-87735)",
                "project_id": project_id,
                "workflow_definition": definition,
            },
        )
        if status not in {200, 201} or not isinstance(payload, dict):
            print(f"create_workflow_failed status={status} body={payload}")
            return 1
        workflow_id = payload["id"]

    status, payload = request(
        "POST",
        "/executions",
        token,
        {
            "workflow_id": workflow_id,
            "trigger_node_id": "trigger",
            "input_data": {"version": "3.2.0", "environment": "production"},
        },
    )
    if status not in {200, 201} or not isinstance(payload, dict):
        print(f"create_execution_failed status={status} body={payload}")
        return 1
    execution_id = payload["id"]

    exec_status = payload.get("status")
    for _ in range(90):
        status, payload = request("GET", f"/executions/{execution_id}", token)
        if status == 200 and isinstance(payload, dict):
            exec_status = payload.get("status")
            if exec_status == "paused":
                break
            if exec_status in {"failed", "cancelled", "completed"}:
                print(f"execution_unexpected status={exec_status} error={payload.get('error_details')}")
                return 1
        time.sleep(1)
    else:
        print(f"execution_timeout status={exec_status}")
        return 1

    approval_id = None
    stored_prompt = None
    for _ in range(30):
        status, payload = request("GET", "/approvals?status=pending&limit=100", token)
        if status == 200 and isinstance(payload, dict):
            for row in payload.get("resources") or []:
                if str(row.get("execution_id")) == str(execution_id):
                    approval_id = row.get("id")
                    stored_prompt = row.get("prompt")
                    break
            if approval_id:
                break
        time.sleep(1)
    if not approval_id:
        print("approval_not_found")
        return 1

    print(f"approval_prompt={stored_prompt}")
    print(f"workflow_id={workflow_id}")
    print(f"execution_id={execution_id}")
    print(f"approval_id={approval_id}")
    print(f"builder={UI}/workflow-builder/{workflow_id}")
    print(f"review={UI}/executions/{execution_id}?approval={approval_id}&history=closed")
    print(f"approvals={UI}/approvals")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
