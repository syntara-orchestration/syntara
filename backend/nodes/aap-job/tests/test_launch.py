"""Preserve implemented job launch overrides."""

from syntara_node_aap_job.executor import _build_launch_body
from syntara_node_runtime.models import AAPJobTemplateExecutorParameters


def test_job_overrides():
    config = AAPJobTemplateExecutorParameters(
        job_template_id=1,
        job_credentials=[9],
        verbosity=0,
        job_slicing=2,
        diff_mode=True,
        tags="setup",
        extra_vars={"x": 1},
    )
    assert _build_launch_body(config, 3, 4) == {
        "inventory": 3,
        "instance_groups": [4],
        "credentials": [9],
        "verbosity": 0,
        "job_slice_count": 2,
        "diff_mode": True,
        "job_tags": "setup",
        "extra_vars": {"x": 1},
    }
