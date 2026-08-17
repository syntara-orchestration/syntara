"""Unit tests for workflow reference validation (extraction + type collection)."""

from uuid import UUID, uuid4

from syntara.workflows.validators.workflow_integrations import (
    _collect_expected_integration_types,
    _extract_integration_ids,
    _extract_llm_model_ids,
    _extract_tool_ids,
)


class TestExtractIntegrationIds:
    """Tests for _extract_integration_ids."""

    def test_extracts_from_integration_connections(self) -> None:
        intg_id = str(uuid4())
        definition = {
            "nodes": [
                {
                    "parameters": {
                        "integration_connections": [
                            {"integration_id": intg_id, "credential_id": str(uuid4())},
                        ]
                    }
                }
            ]
        }
        result = _extract_integration_ids(definition)
        assert result == {intg_id}

    def test_extracts_multiple_from_multiple_nodes(self) -> None:
        id1, id2 = str(uuid4()), str(uuid4())
        definition = {
            "nodes": [
                {"parameters": {"integration_connections": [{"integration_id": id1}]}},
                {"parameters": {"integration_connections": [{"integration_id": id2}]}},
            ]
        }
        result = _extract_integration_ids(definition)
        assert result == {id1, id2}

    def test_deduplicates(self) -> None:
        intg_id = str(uuid4())
        definition = {
            "nodes": [
                {
                    "parameters": {
                        "integration_connections": [
                            {"integration_id": intg_id},
                            {"integration_id": intg_id},
                        ]
                    }
                }
            ]
        }
        result = _extract_integration_ids(definition)
        assert result == {intg_id}

    def test_skips_template_expressions(self) -> None:
        definition = {
            "nodes": [
                {
                    "parameters": {
                        "integration_connections": [
                            {"integration_id": "{{ env.INTEGRATION_ID }}"},
                        ]
                    }
                }
            ]
        }
        result = _extract_integration_ids(definition)
        assert result == set()

    def test_skips_missing_integration_id(self) -> None:
        definition = {"nodes": [{"parameters": {"integration_connections": [{"credential_id": str(uuid4())}]}}]}
        result = _extract_integration_ids(definition)
        assert result == set()

    def test_handles_no_nodes(self) -> None:
        assert _extract_integration_ids({"nodes": []}) == set()
        assert _extract_integration_ids({}) == set()

    def test_handles_no_parameters(self) -> None:
        definition: dict[str, list[dict[str, str]]] = {"nodes": [{}]}
        assert _extract_integration_ids(definition) == set()

    def test_handles_no_integration_connections(self) -> None:
        definition = {"nodes": [{"parameters": {"prompt": "hello"}}]}
        assert _extract_integration_ids(definition) == set()

    def test_extracts_direct_integration_id_from_aap_node(self) -> None:
        intg_id = str(uuid4())
        definition = {"nodes": [{"parameters": {"integration_id": intg_id, "credential_id": str(uuid4())}}]}
        result = _extract_integration_ids(definition)
        assert result == {intg_id}

    def test_extracts_both_direct_and_connection_ids(self) -> None:
        aap_id = str(uuid4())
        mcp_id = str(uuid4())
        definition = {
            "nodes": [
                {"parameters": {"integration_id": aap_id}},
                {"parameters": {"integration_connections": [{"integration_id": mcp_id}]}},
            ]
        }
        result = _extract_integration_ids(definition)
        assert result == {aap_id, mcp_id}

    def test_skips_template_in_direct_integration_id(self) -> None:
        definition = {"nodes": [{"parameters": {"integration_id": "{{ env.AAP_INTEGRATION }}"}}]}
        result = _extract_integration_ids(definition)
        assert result == set()


class TestExtractLlmModelIds:
    """Tests for _extract_llm_model_ids."""

    def test_extracts_llm_model_id(self) -> None:
        model_id = str(uuid4())
        definition = {"nodes": [{"parameters": {"llm_model_id": model_id}}]}
        result = _extract_llm_model_ids(definition)
        assert result == {model_id}

    def test_skips_empty_llm_model_id(self) -> None:
        definition = {"nodes": [{"parameters": {"llm_model_id": ""}}]}
        result = _extract_llm_model_ids(definition)
        assert result == set()

    def test_skips_template_in_llm_model_id(self) -> None:
        definition = {"nodes": [{"parameters": {"llm_model_id": "{{ env.MODEL }}"}}]}
        result = _extract_llm_model_ids(definition)
        assert result == set()

    def test_extracts_from_multiple_nodes(self) -> None:
        m1, m2 = str(uuid4()), str(uuid4())
        definition = {
            "nodes": [
                {"parameters": {"llm_model_id": m1}},
                {"parameters": {"llm_model_id": m2}},
            ]
        }
        result = _extract_llm_model_ids(definition)
        assert result == {m1, m2}

    def test_handles_no_llm_model_id(self) -> None:
        definition = {"nodes": [{"parameters": {"prompt": "hello"}}]}
        result = _extract_llm_model_ids(definition)
        assert result == set()


class TestCollectExpectedIntegrationTypes:
    """Tests for _collect_expected_integration_types."""

    def test_aap_node_expects_aap_type(self) -> None:
        intg_id = str(uuid4())
        definition = {"nodes": [{"type": "aap_job_template", "parameters": {"integration_id": intg_id}}]}
        result = _collect_expected_integration_types(definition)
        assert result[UUID(intg_id)] == "ansible_automation_platform"

    def test_aap_workflow_template_expects_aap_type(self) -> None:
        intg_id = str(uuid4())
        definition = {"nodes": [{"type": "aap_workflow_job_template", "parameters": {"integration_id": intg_id}}]}
        result = _collect_expected_integration_types(definition)
        assert result[UUID(intg_id)] == "ansible_automation_platform"

    def test_agentic_connection_expects_mcp_type(self) -> None:
        intg_id = str(uuid4())
        definition = {
            "nodes": [
                {
                    "type": "agentic",
                    "parameters": {"integration_connections": [{"integration_id": intg_id}]},
                }
            ]
        }
        result = _collect_expected_integration_types(definition)
        assert result[UUID(intg_id)] == "mcp_server"

    def test_mixed_nodes(self) -> None:
        aap_id = str(uuid4())
        mcp_id = str(uuid4())
        definition = {
            "nodes": [
                {"type": "aap_job_template", "parameters": {"integration_id": aap_id}},
                {"type": "agentic", "parameters": {"integration_connections": [{"integration_id": mcp_id}]}},
            ]
        }
        result = _collect_expected_integration_types(definition)
        assert result[UUID(aap_id)] == "ansible_automation_platform"
        assert result[UUID(mcp_id)] == "mcp_server"

    def test_script_node_ignored(self) -> None:
        definition = {"nodes": [{"type": "script", "parameters": {"language": "python"}}]}
        result = _collect_expected_integration_types(definition)
        assert result == {}

    def test_skips_template_expressions(self) -> None:
        definition = {"nodes": [{"type": "aap_job_template", "parameters": {"integration_id": "{{ env.ID }}"}}]}
        result = _collect_expected_integration_types(definition)
        assert result == {}


class TestExtractToolIds:
    """Tests for _extract_tool_ids."""

    def test_extracts_tool_ids_from_selected_strategy(self) -> None:
        t1, t2 = str(uuid4()), str(uuid4())
        definition = {
            "nodes": [
                {
                    "parameters": {
                        "tool_selection_strategy": "SELECTED",
                        "tool_selections": [t1, t2],
                    }
                }
            ]
        }
        result = _extract_tool_ids(definition)
        assert result == {t1, t2}

    def test_skips_all_strategy(self) -> None:
        definition = {
            "nodes": [
                {
                    "parameters": {
                        "tool_selection_strategy": "ALL",
                        "tool_selections": [str(uuid4())],
                    }
                }
            ]
        }
        result = _extract_tool_ids(definition)
        assert result == set()

    def test_skips_none_strategy(self) -> None:
        definition = {
            "nodes": [
                {
                    "parameters": {
                        "tool_selection_strategy": "NONE",
                        "tool_selections": [],
                    }
                }
            ]
        }
        result = _extract_tool_ids(definition)
        assert result == set()

    def test_skips_null_strategy(self) -> None:
        definition = {"nodes": [{"parameters": {"tool_selections": [str(uuid4())]}}]}
        result = _extract_tool_ids(definition)
        assert result == set()

    def test_skips_template_expressions(self) -> None:
        definition = {
            "nodes": [
                {
                    "parameters": {
                        "tool_selection_strategy": "SELECTED",
                        "tool_selections": ["${tools.MY_TOOL}"],
                    }
                }
            ]
        }
        result = _extract_tool_ids(definition)
        assert result == set()

    def test_deduplicates(self) -> None:
        tid = str(uuid4())
        definition = {
            "nodes": [
                {
                    "parameters": {
                        "tool_selection_strategy": "SELECTED",
                        "tool_selections": [tid, tid],
                    }
                }
            ]
        }
        result = _extract_tool_ids(definition)
        assert result == {tid}

    def test_extracts_from_multiple_nodes(self) -> None:
        t1, t2 = str(uuid4()), str(uuid4())
        definition = {
            "nodes": [
                {"parameters": {"tool_selection_strategy": "SELECTED", "tool_selections": [t1]}},
                {"parameters": {"tool_selection_strategy": "SELECTED", "tool_selections": [t2]}},
            ]
        }
        result = _extract_tool_ids(definition)
        assert result == {t1, t2}

    def test_handles_no_nodes(self) -> None:
        assert _extract_tool_ids({"nodes": []}) == set()
        assert _extract_tool_ids({}) == set()

    def test_handles_no_tool_selections(self) -> None:
        definition = {"nodes": [{"parameters": {"tool_selection_strategy": "SELECTED"}}]}
        result = _extract_tool_ids(definition)
        assert result == set()

    def test_mixed_valid_and_template(self) -> None:
        tid = str(uuid4())
        definition = {
            "nodes": [
                {
                    "parameters": {
                        "tool_selection_strategy": "SELECTED",
                        "tool_selections": [tid, "${tools.OTHER}"],
                    }
                }
            ]
        }
        result = _extract_tool_ids(definition)
        assert result == {tid}

    def test_skips_empty_and_malformed_ids(self) -> None:
        t1, t2 = str(uuid4()), str(uuid4())
        definition = {
            "nodes": [
                {
                    "parameters": {
                        "tool_selection_strategy": "SELECTED",
                        "tool_selections": [t1, "", "not-a-uuid", t2],
                    }
                }
            ]
        }
        result = _extract_tool_ids(definition)
        assert result == {t1, t2}
