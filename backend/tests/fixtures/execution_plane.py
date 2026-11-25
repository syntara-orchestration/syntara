"""Execution Plane plugin registry test fixtures."""

from __future__ import annotations

from typing import Any

SCRIPT_PYTHON_TEST_IMAGE_REFERENCE = "registry.example/test/ao-python@sha256:" + "a" * 64
SCRIPT_BASH_TEST_IMAGE_REFERENCE = "registry.example/test/ao-bash@sha256:" + "b" * 64

ECHO_ACTION_MANIFEST: dict[str, Any] = {
    "apiVersion": "syntara.io/v1alpha1",
    "kind": "Action",
    "metadata": {
        "name": "echo",
        "displayName": "Echo",
        "description": "Echoes a message to an Echo workspace.",
    },
    "spec": {
        "integrationType": "acme.echo.connection",
        "runtime": {"kind": "custom-runner", "entryPoint": "acme_echo.runtime:EchoStep"},
        "input": {
            "kind": "inline",
            "value": {
                "type": "object",
                "title": "EchoInput",
                "additionalProperties": False,
                "required": ["message", "workspaceId"],
                "properties": {
                    "message": {"title": "Message", "type": "string", "minLength": 1},
                    "workspaceId": {"title": "Workspace ID", "type": "string", "minLength": 1},
                },
            },
        },
        "output": {
            "kind": "inline",
            "value": {
                "type": "object",
                "title": "EchoOutput",
                "additionalProperties": False,
                "required": ["message"],
                "properties": {"message": {"type": "string"}},
            },
        },
        "error": {"kind": "inline", "value": {"type": "object"}},
    },
}

ECHO_INTEGRATION_TYPE_MANIFEST: dict[str, Any] = {
    "apiVersion": "syntara.io/v1alpha1",
    "kind": "IntegrationType",
    "metadata": {
        "name": "connection",
        "displayName": "Echo connection",
        "description": "Connection to the Echo service.",
    },
    "spec": {
        "id": "acme.echo.connection",
        "endpointKinds": ["https"],
        "credentialTypes": ["acme.echo.api-token", "acme.echo.workspace-token"],
        "configuration": {"kind": "inline", "value": {"type": "object", "additionalProperties": False}},
    },
}

ECHO_API_TOKEN_RECIPE_MANIFEST: dict[str, Any] = {
    "apiVersion": "syntara.io/v1alpha1",
    "kind": "CredentialRecipe",
    "metadata": {
        "name": "api-token",
        "displayName": "Echo API token",
        "description": "User-level token used to authenticate to the Echo API.",
    },
    "spec": {
        "id": "acme.echo.api-token",
        "integrationType": "acme.echo.connection",
        "credentialSchema": {
            "kind": "inline",
            "value": {
                "type": "object",
                "title": "EchoApiTokenCredential",
                "additionalProperties": False,
                "required": ["token"],
                "properties": {"token": {"title": "API token", "type": "string", "minLength": 8}},
            },
        },
        "secretFields": ["token"],
        "issuance": {"kind": "static-bearer.v1"},
    },
}

ECHO_WORKSPACE_TOKEN_RECIPE_MANIFEST: dict[str, Any] = {
    "apiVersion": "syntara.io/v1alpha1",
    "kind": "CredentialRecipe",
    "metadata": {
        "name": "workspace-token",
        "displayName": "Echo workspace token",
        "description": "Workspace-scoped token used to authorize changes in a workspace.",
    },
    "spec": {
        "id": "acme.echo.workspace-token",
        "integrationType": "acme.echo.connection",
        "credentialSchema": {
            "kind": "inline",
            "value": {
                "type": "object",
                "title": "EchoWorkspaceTokenCredential",
                "additionalProperties": False,
                "required": ["workspaceToken"],
                "properties": {"workspaceToken": {"title": "Workspace token", "type": "string", "minLength": 8}},
            },
        },
        "secretFields": ["workspaceToken"],
        "issuance": {"kind": "static-bearer.v1"},
    },
}
