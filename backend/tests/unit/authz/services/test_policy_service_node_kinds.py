"""Unit tests for node-kind statement validation in the policy service."""

import pytest

from syntara.authz.exceptions import InvalidNodeKindError
from syntara.authz.services.policy_service import PolicyService


class TestValidateNodeKindStatements:
    """The policy service rejects workflow_node statements with unknown kinds."""

    def test_unknown_kind_raises(self) -> None:
        statements = [
            {
                "effect": "allow",
                "actions": ["workflow_node:write"],
                "scope": "any",
                "conditions": {"resource_labels": {"kind": "bogus"}},
            }
        ]
        with pytest.raises(InvalidNodeKindError, match="Unknown node kind 'bogus'"):
            PolicyService._validate_node_kind_statements(statements)

    def test_valid_kind_passes(self) -> None:
        statements = [
            {
                "effect": "allow",
                "actions": ["workflow_node:write"],
                "scope": "any",
                "conditions": {"resource_labels": {"kind": "script"}},
            }
        ]
        PolicyService._validate_node_kind_statements(statements)

    def test_statements_without_workflow_node_actions_pass(self) -> None:
        statements = [
            {
                "effect": "allow",
                "actions": ["workflow:read"],
                "scope": "any",
                "conditions": {"resource_labels": {"kind": "bogus"}},
            }
        ]
        PolicyService._validate_node_kind_statements(statements)

    def test_empty_statements_pass(self) -> None:
        PolicyService._validate_node_kind_statements([])
