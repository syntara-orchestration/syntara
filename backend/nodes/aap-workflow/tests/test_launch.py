"""Preserve implemented workflow launch overrides."""

from syntara_node_aap_workflow.executor import _build_launch_body
from syntara_node_runtime.models import AAPWorkflowJobTemplateExecutorParameters


def test_workflow_overrides():
    config = AAPWorkflowJobTemplateExecutorParameters(
        workflow_job_template_id=1, scm_branch="release", tags="setup", extra_vars={"x": 1}
    )
    assert _build_launch_body(config, 3) == {
        "inventory": 3,
        "scm_branch": "release",
        "job_tags": "setup",
        "extra_vars": {"x": 1},
    }
