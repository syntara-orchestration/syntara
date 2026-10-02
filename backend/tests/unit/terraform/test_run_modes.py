"""Unit tests for TFE run mode mapping."""

import pytest

from syntara.terraform.errors import TFEError, TFEErrorCode
from syntara.terraform.run_modes import map_run_mode


def test_plan_only_mode() -> None:
    attrs = map_run_mode("plan-only")
    assert attrs == {"plan-only": True}


def test_plan_and_apply_mode() -> None:
    attrs = map_run_mode("plan-and-apply", message="hi")
    assert attrs["plan-only"] is False
    assert attrs["auto-apply"] is True
    assert attrs["message"] == "hi"


def test_targeted_resource_requires_addresses() -> None:
    with pytest.raises(TFEError) as exc:
        map_run_mode("targeted-resource")
    assert exc.value.error_code == TFEErrorCode.VALIDATION


def test_targeted_resource_with_addresses() -> None:
    attrs = map_run_mode("targeted-resource", target_resources=["aws_instance.a"])
    assert attrs["target-addrs"] == ["aws_instance.a"]


def test_unsupported_mode() -> None:
    with pytest.raises(TFEError) as exc:
        map_run_mode("nope")
    assert exc.value.error_code == TFEErrorCode.VALIDATION
