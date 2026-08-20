#!/usr/bin/env python3
"""
Create a workflow from JSON using the Syntara API.

This tool is designed for PR reviews - paste JSON directly or use a file.

Usage:
    # From a file
    python create_workflow.py workflow.json

    # From stdin (paste JSON)
    python create_workflow.py -

    # Pipe JSON directly
    echo '{"name": "test", ...}' | python create_workflow.py -

    # With options
    python create_workflow.py workflow.json --name "my-workflow"
    python create_workflow.py - --dry-run
"""

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

DEFAULT_API_URL = "http://localhost:8000"


def load_json(source: str) -> dict:
    """Load JSON from file or stdin."""
    # Read from stdin if source is "-"
    if source == "-":
        print("Reading JSON from stdin (paste JSON, then Ctrl+D when done)...")
        try:
            content = sys.stdin.read()
            return json.loads(content)
        except json.JSONDecodeError as e:
            print(f"Error: Invalid JSON from stdin: {e}")
            sys.exit(1)

    # Read from file
    path = Path(source)
    if not path.exists():
        print(f"Error: File not found: {source}")
        sys.exit(1)

    with open(path, "r") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError as e:
            print(f"Error: Invalid JSON in {source}: {e}")
            sys.exit(1)


def check_api_health(api_url: str) -> bool:
    """Check if the API is healthy."""
    try:
        req = urllib.request.Request(f"{api_url}/healthz/ready", method="GET")
        with urllib.request.urlopen(req, timeout=5) as response:
            return response.status == 200
    except (urllib.error.URLError, urllib.error.HTTPError) as e:
        print(f"Error: Cannot connect to API at {api_url}: {e}")
        return False


def create_workflow(api_url: str, payload: dict) -> dict:
    """Create a workflow via the API."""
    url = f"{api_url}/api/v1/workflows"
    data = json.dumps(payload).encode("utf-8")

    try:
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8")
        try:
            error_detail = json.loads(error_body).get("detail", error_body)
        except json.JSONDecodeError:
            error_detail = error_body
        print(f"Error: API returned {e.code}: {error_detail}")
        sys.exit(1)
    except urllib.error.URLError as e:
        print(f"Error: Request failed: {e}")
        sys.exit(1)


def build_payload(data: dict, name_override: str = None) -> dict:
    """
    Build the API payload from JSON data.

    Supports three formats:
    1. API response format (exported workflow with version.workflow_definition)
    2. Simple format with top-level workflow_definition
    3. Direct workflow definition format (version, metadata, triggers, workflow)
    """
    # Format 1: API response format (exported from GET /workflows/{id})
    # Has nested structure: version.workflow_definition
    if "version" in data and isinstance(data["version"], dict):
        version_data = data["version"]
        if "workflow_definition" in version_data:
            workflow_definition = version_data["workflow_definition"]
            name = name_override or data.get("name", "unnamed-workflow")
            description = data.get("description", "")

            return {
                "name": name,
                "description": description,
                "is_enabled": data.get("is_enabled", True),
                "workflow_definition": workflow_definition,
                "labels": data.get("labels", {}),
            }

    # Format 2: Direct workflow definition (has 'workflow' but not 'workflow_definition')
    if "workflow" in data and "workflow_definition" not in data:
        workflow_definition = data
        name = name_override or data.get("metadata", {}).get("name", "unnamed-workflow")
        description = data.get("metadata", {}).get("description", "")

        return {
            "name": name,
            "description": description,
            "is_enabled": True,
            "workflow_definition": workflow_definition,
        }

    # Format 3: Simple format with workflow_definition at top level
    payload = {
        "name": name_override or data.get("name", "unnamed-workflow"),
        "description": data.get("description", ""),
        "is_enabled": data.get("is_enabled", True),
        "workflow_definition": data.get("workflow_definition", data),
    }

    if "labels" in data:
        payload["labels"] = data["labels"]

    return payload


DEFAULT_EXAMPLE = "tools/workflow-creator/examples/hello-world.json"


def main():
    parser = argparse.ArgumentParser(
        description="Create a workflow from JSON using the Syntara API.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                                  # Use default example
  %(prog)s workflow.json                    # From file
  %(prog)s -                                # From stdin (paste JSON)
  %(prog)s - --name "pr-review"             # From stdin with custom name
  %(prog)s workflow.json --dry-run          # Preview without creating
        """,
    )
    parser.add_argument(
        "json_source",
        nargs="?",
        default=DEFAULT_EXAMPLE,
        help=f"JSON file path, or '-' for stdin (default: {DEFAULT_EXAMPLE})",
    )
    parser.add_argument(
        "--api-url",
        default=DEFAULT_API_URL,
        help=f"API base URL (default: {DEFAULT_API_URL})",
    )
    parser.add_argument(
        "--name",
        help="Override the workflow name",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show the payload without creating the workflow",
    )

    args = parser.parse_args()

    # Load JSON from file or stdin
    if args.json_source != "-":
        print(f"Loading: {args.json_source}")
    data = load_json(args.json_source)

    # Build payload
    payload = build_payload(data, args.name)
    print(f"Workflow name: {payload['name']}")

    if args.dry_run:
        print("\n--- Dry run: Payload that would be sent ---")
        print(json.dumps(payload, indent=2))
        return

    # Check API health
    if not check_api_health(args.api_url):
        sys.exit(1)

    # Create workflow
    print(f"Creating workflow via {args.api_url}...")
    result = create_workflow(args.api_url, payload)

    print(f"\n✓ Workflow created successfully!")
    print(f"  ID: {result['id']}")
    print(f"  Name: {result['name']}")
    print(f"  Version: {result.get('current_version', 1)}")


if __name__ == "__main__":
    main()
