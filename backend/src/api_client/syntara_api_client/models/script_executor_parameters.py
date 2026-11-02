from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.script_language import ScriptLanguage
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.execution_target_profile import ExecutionTargetProfile
    from ..models.script_executor_parameters_environment import ScriptExecutorParametersEnvironment


T = TypeVar("T", bound="ScriptExecutorParameters")


@_attrs_define
class ScriptExecutorParameters:
    """Parameters for script executor.

    Attributes:
        language (ScriptLanguage): Supported script languages for script executor.
        code (str): Script code to execute
        execution_profile (ExecutionTargetProfile | None | Unset): Execution Plane placement profile for this workload.
        environment (ScriptExecutorParametersEnvironment | Unset): Environment variables
    """

    language: ScriptLanguage
    code: str
    execution_profile: ExecutionTargetProfile | None | Unset = UNSET
    environment: ScriptExecutorParametersEnvironment | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.execution_target_profile import ExecutionTargetProfile

        language = self.language.value

        code = self.code

        execution_profile: dict[str, Any] | None | Unset
        if isinstance(self.execution_profile, Unset):
            execution_profile = UNSET
        elif isinstance(self.execution_profile, ExecutionTargetProfile):
            execution_profile = self.execution_profile.to_dict()
        else:
            execution_profile = self.execution_profile

        environment: dict[str, Any] | Unset = UNSET
        if not isinstance(self.environment, Unset):
            environment = self.environment.to_dict()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "language": language,
                "code": code,
            }
        )
        if execution_profile is not UNSET:
            field_dict["execution_profile"] = execution_profile
        if environment is not UNSET:
            field_dict["environment"] = environment

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.execution_target_profile import ExecutionTargetProfile
        from ..models.script_executor_parameters_environment import ScriptExecutorParametersEnvironment

        d = dict(src_dict)
        language = ScriptLanguage(d.pop("language"))

        code = d.pop("code")

        def _parse_execution_profile(data: object) -> ExecutionTargetProfile | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                execution_profile_type_0 = ExecutionTargetProfile.from_dict(data)

                return execution_profile_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(ExecutionTargetProfile | None | Unset, data)

        execution_profile = _parse_execution_profile(d.pop("execution_profile", UNSET))

        _environment = d.pop("environment", UNSET)
        environment: ScriptExecutorParametersEnvironment | Unset
        if isinstance(_environment, Unset):
            environment = UNSET
        else:
            environment = ScriptExecutorParametersEnvironment.from_dict(_environment)

        script_executor_parameters = cls(
            language=language,
            code=code,
            execution_profile=execution_profile,
            environment=environment,
        )

        script_executor_parameters.additional_properties = d
        return script_executor_parameters

    @property
    def additional_keys(self) -> list[str]:
        return list(self.additional_properties.keys())

    def __getitem__(self, key: str) -> Any:
        return self.additional_properties[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self.additional_properties[key] = value

    def __delitem__(self, key: str) -> None:
        del self.additional_properties[key]

    def __contains__(self, key: str) -> bool:
        return key in self.additional_properties
