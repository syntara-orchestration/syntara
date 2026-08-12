"""Unit tests for AgentState and AgentStateFactory."""

from uuid import UUID, uuid4

from syntara.agent_orchestrator.models.agent_state import AgentStateFactory
from syntara.audit.emitter import AuditActorContext


class TestAgentStateFactory:
    """Tests for AgentStateFactory.create_initial_state."""

    def test_execution_id_defaults_to_none(self):
        state = AgentStateFactory.create_initial_state(
            prompt="test", session_id="sess-1", invocation_id=uuid4(), actor_context=AuditActorContext()
        )
        assert state.get("execution_id") is None

    def test_execution_id_set_when_provided(self):
        exec_id = UUID("550e8400-e29b-41d4-a716-446655440000")
        state = AgentStateFactory.create_initial_state(
            prompt="test",
            session_id="sess-1",
            invocation_id=uuid4(),
            execution_id=exec_id,
            actor_context=AuditActorContext(),
        )
        assert state["execution_id"] == exec_id

    def test_execution_id_accessible_in_state_dict(self):
        exec_id = uuid4()
        state = AgentStateFactory.create_initial_state(
            prompt="test",
            session_id="sess-1",
            invocation_id=uuid4(),
            execution_id=exec_id,
            actor_context=AuditActorContext(),
        )
        assert state.get("execution_id") == exec_id
