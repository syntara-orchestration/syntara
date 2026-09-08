from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.script_language import ScriptLanguage
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.script_executor_parameters_environment import ScriptExecutorParametersEnvironment


T = TypeVar("T", bound="ScriptExecutorParameters")


@_attrs_define
class ScriptExecutorParameters:
    """Parameters for script executor.

    Attributes:
        language (ScriptLanguage): Supported script languages for script executor.
        code (str): Script code to execute
        environment (ScriptExecutorParametersEnvironment | Unset): Environment variables
    """

    language: ScriptLanguage
    code: str
    environment: ScriptExecutorParametersEnvironment | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        language = self.language.value

        code = self.code

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
        if environment is not UNSET:
            field_dict["environment"] = environment

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.script_executor_parameters_environment import ScriptExecutorParametersEnvironment

        d = dict(src_dict)
        language = ScriptLanguage(d.pop("language"))

        code = d.pop("code")

        _environment = d.pop("environment", UNSET)
        environment: ScriptExecutorParametersEnvironment | Unset
        if isinstance(_environment, Unset):
            environment = UNSET
        else:
            environment = ScriptExecutorParametersEnvironment.from_dict(_environment)

        script_executor_parameters = cls(
            language=language,
            code=code,
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
