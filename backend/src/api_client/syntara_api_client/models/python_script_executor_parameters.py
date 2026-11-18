from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.credential_binding import CredentialBinding
    from ..models.execution_target_profile import ExecutionTargetProfile
    from ..models.python_script_executor_parameters_environment import PythonScriptExecutorParametersEnvironment


T = TypeVar("T", bound="PythonScriptExecutorParameters")


@_attrs_define
class PythonScriptExecutorParameters:
    """Parameters for the Python script executor.

    Attributes:
        code (str): Script code to execute
        execution_profile (ExecutionTargetProfile | None | Unset): Execution Plane placement profile for this workload.
        environment (PythonScriptExecutorParametersEnvironment | Unset): Environment variables
        credential_bindings (list[CredentialBinding] | Unset): Host-side recipe-to-credential bindings for Execution
            Plane dispatch.
    """

    code: str
    execution_profile: ExecutionTargetProfile | None | Unset = UNSET
    environment: PythonScriptExecutorParametersEnvironment | Unset = UNSET
    credential_bindings: list[CredentialBinding] | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        from ..models.execution_target_profile import ExecutionTargetProfile

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

        credential_bindings: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.credential_bindings, Unset):
            credential_bindings = []
            for credential_bindings_item_data in self.credential_bindings:
                credential_bindings_item = credential_bindings_item_data.to_dict()
                credential_bindings.append(credential_bindings_item)

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "code": code,
            }
        )
        if execution_profile is not UNSET:
            field_dict["execution_profile"] = execution_profile
        if environment is not UNSET:
            field_dict["environment"] = environment
        if credential_bindings is not UNSET:
            field_dict["credential_bindings"] = credential_bindings

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.credential_binding import CredentialBinding
        from ..models.execution_target_profile import ExecutionTargetProfile
        from ..models.python_script_executor_parameters_environment import PythonScriptExecutorParametersEnvironment

        d = dict(src_dict)
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
        environment: PythonScriptExecutorParametersEnvironment | Unset
        if isinstance(_environment, Unset):
            environment = UNSET
        else:
            environment = PythonScriptExecutorParametersEnvironment.from_dict(_environment)

        _credential_bindings = d.pop("credential_bindings", UNSET)
        credential_bindings: list[CredentialBinding] | Unset = UNSET
        if _credential_bindings is not UNSET:
            credential_bindings = []
            for credential_bindings_item_data in _credential_bindings:
                credential_bindings_item = CredentialBinding.from_dict(credential_bindings_item_data)

                credential_bindings.append(credential_bindings_item)

        python_script_executor_parameters = cls(
            code=code,
            execution_profile=execution_profile,
            environment=environment,
            credential_bindings=credential_bindings,
        )

        return python_script_executor_parameters
