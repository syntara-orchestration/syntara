from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.aap_job_type import AAPJobType
from ..models.aap_verbosity import AAPVerbosity
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.aap_job_template_executor_parameters_extra_vars import AAPJobTemplateExecutorParametersExtraVars


T = TypeVar("T", bound="AAPJobTemplateExecutorParameters")


@_attrs_define
class AAPJobTemplateExecutorParameters:
    """Parameters for Ansible Automation Platform Job Template executor.

    Inherits common Ansible Automation Platform fields from AAPResourceReferenceMixin (credential_id, organization,
    inventory, extra_vars, limit, tags, skip_tags, labels, timeout).

        Attributes:
            credential_id (None | str | Unset): Nexus credential UUID for Ansible Automation Platform API authentication.
                Separate from legacy credentials list.
            integration_id (None | str | Unset): UUID of the Ansible Automation Platform Gateway integration for connection
                URL resolution.
            organization_id (int | None | Unset): Ansible Automation Platform organization ID (takes precedence over
                organization_name)
            organization_name (None | str | Unset): Ansible Automation Platform organization name (used with template_name
                or inventory_name)
            inventory_id (int | None | Unset): Override default inventory by ID (mutually exclusive with inventory_name)
            inventory_name (None | str | Unset): Override default inventory by name (requires organization_name)
            extra_vars (AAPJobTemplateExecutorParametersExtraVars | Unset): Extra variables to pass to job/workflow job
            limit (None | str | Unset): Limit job execution to specific hosts
            tags (None | str | Unset): Ansible tags to run (comma-separated)
            skip_tags (None | str | Unset): Ansible tags to skip (comma-separated)
            labels (list[str] | None | Unset): Ansible Automation Platform label names to append to template's default
                labels. Names are resolved to IDs at launch time. New labels that don't exist in Ansible Automation Platform
                will be created automatically. Note: Labels are APPENDED to template defaults, not replaced.
            job_template_id (int | None | Unset): Ansible Automation Platform job template ID to launch
            job_template_name (None | str | Unset): Ansible Automation Platform job template name (used with
                organization_name)
            job_credentials (list[int] | None | Unset): List of Ansible Automation Platform credential IDs to use (takes
                precedence over credential_names)
            credential_names (list[str] | None | Unset): List of Ansible Automation Platform credential names to use
                (requires organization_name, resolved at launch time)
            verbosity (AAPVerbosity | Unset): Ansible Automation Platform job verbosity levels (0-5).
            job_type (AAPJobType | None | Unset): Job type override: 'run' or 'check' (dry run)
            forks (int | None | Unset): Number of parallel forks for job execution
            job_slicing (int | None | Unset): Number of job slices
            diff_mode (bool | None | Unset): Enable diff mode for playbook runs
            execution_environment (None | str | Unset): Execution environment override (deferred — requires ID resolution)
            instance_group_id (int | None | Unset): Override instance group by ID (takes precedence over
                instance_group_name)
            instance_group_name (None | str | Unset): Override instance group by name (requires organization_name for
                lookup)
    """

    credential_id: None | str | Unset = UNSET
    integration_id: None | str | Unset = UNSET
    organization_id: int | None | Unset = UNSET
    organization_name: None | str | Unset = UNSET
    inventory_id: int | None | Unset = UNSET
    inventory_name: None | str | Unset = UNSET
    extra_vars: AAPJobTemplateExecutorParametersExtraVars | Unset = UNSET
    limit: None | str | Unset = UNSET
    tags: None | str | Unset = UNSET
    skip_tags: None | str | Unset = UNSET
    labels: list[str] | None | Unset = UNSET
    job_template_id: int | None | Unset = UNSET
    job_template_name: None | str | Unset = UNSET
    job_credentials: list[int] | None | Unset = UNSET
    credential_names: list[str] | None | Unset = UNSET
    verbosity: AAPVerbosity | Unset = UNSET
    job_type: AAPJobType | None | Unset = UNSET
    forks: int | None | Unset = UNSET
    job_slicing: int | None | Unset = UNSET
    diff_mode: bool | None | Unset = UNSET
    execution_environment: None | str | Unset = UNSET
    instance_group_id: int | None | Unset = UNSET
    instance_group_name: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        credential_id: None | str | Unset
        if isinstance(self.credential_id, Unset):
            credential_id = UNSET
        else:
            credential_id = self.credential_id

        integration_id: None | str | Unset
        if isinstance(self.integration_id, Unset):
            integration_id = UNSET
        else:
            integration_id = self.integration_id

        organization_id: int | None | Unset
        if isinstance(self.organization_id, Unset):
            organization_id = UNSET
        else:
            organization_id = self.organization_id

        organization_name: None | str | Unset
        if isinstance(self.organization_name, Unset):
            organization_name = UNSET
        else:
            organization_name = self.organization_name

        inventory_id: int | None | Unset
        if isinstance(self.inventory_id, Unset):
            inventory_id = UNSET
        else:
            inventory_id = self.inventory_id

        inventory_name: None | str | Unset
        if isinstance(self.inventory_name, Unset):
            inventory_name = UNSET
        else:
            inventory_name = self.inventory_name

        extra_vars: dict[str, Any] | Unset = UNSET
        if not isinstance(self.extra_vars, Unset):
            extra_vars = self.extra_vars.to_dict()

        limit: None | str | Unset
        if isinstance(self.limit, Unset):
            limit = UNSET
        else:
            limit = self.limit

        tags: None | str | Unset
        if isinstance(self.tags, Unset):
            tags = UNSET
        else:
            tags = self.tags

        skip_tags: None | str | Unset
        if isinstance(self.skip_tags, Unset):
            skip_tags = UNSET
        else:
            skip_tags = self.skip_tags

        labels: list[str] | None | Unset
        if isinstance(self.labels, Unset):
            labels = UNSET
        elif isinstance(self.labels, list):
            labels = self.labels

        else:
            labels = self.labels

        job_template_id: int | None | Unset
        if isinstance(self.job_template_id, Unset):
            job_template_id = UNSET
        else:
            job_template_id = self.job_template_id

        job_template_name: None | str | Unset
        if isinstance(self.job_template_name, Unset):
            job_template_name = UNSET
        else:
            job_template_name = self.job_template_name

        job_credentials: list[int] | None | Unset
        if isinstance(self.job_credentials, Unset):
            job_credentials = UNSET
        elif isinstance(self.job_credentials, list):
            job_credentials = self.job_credentials

        else:
            job_credentials = self.job_credentials

        credential_names: list[str] | None | Unset
        if isinstance(self.credential_names, Unset):
            credential_names = UNSET
        elif isinstance(self.credential_names, list):
            credential_names = self.credential_names

        else:
            credential_names = self.credential_names

        verbosity: int | Unset = UNSET
        if not isinstance(self.verbosity, Unset):
            verbosity = self.verbosity.value

        job_type: None | str | Unset
        if isinstance(self.job_type, Unset):
            job_type = UNSET
        elif isinstance(self.job_type, AAPJobType):
            job_type = self.job_type.value
        else:
            job_type = self.job_type

        forks: int | None | Unset
        if isinstance(self.forks, Unset):
            forks = UNSET
        else:
            forks = self.forks

        job_slicing: int | None | Unset
        if isinstance(self.job_slicing, Unset):
            job_slicing = UNSET
        else:
            job_slicing = self.job_slicing

        diff_mode: bool | None | Unset
        if isinstance(self.diff_mode, Unset):
            diff_mode = UNSET
        else:
            diff_mode = self.diff_mode

        execution_environment: None | str | Unset
        if isinstance(self.execution_environment, Unset):
            execution_environment = UNSET
        else:
            execution_environment = self.execution_environment

        instance_group_id: int | None | Unset
        if isinstance(self.instance_group_id, Unset):
            instance_group_id = UNSET
        else:
            instance_group_id = self.instance_group_id

        instance_group_name: None | str | Unset
        if isinstance(self.instance_group_name, Unset):
            instance_group_name = UNSET
        else:
            instance_group_name = self.instance_group_name

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if credential_id is not UNSET:
            field_dict["credential_id"] = credential_id
        if integration_id is not UNSET:
            field_dict["integration_id"] = integration_id
        if organization_id is not UNSET:
            field_dict["organizationId"] = organization_id
        if organization_name is not UNSET:
            field_dict["organization_name"] = organization_name
        if inventory_id is not UNSET:
            field_dict["inventory_id"] = inventory_id
        if inventory_name is not UNSET:
            field_dict["inventory_name"] = inventory_name
        if extra_vars is not UNSET:
            field_dict["extra_vars"] = extra_vars
        if limit is not UNSET:
            field_dict["limit"] = limit
        if tags is not UNSET:
            field_dict["tags"] = tags
        if skip_tags is not UNSET:
            field_dict["skip_tags"] = skip_tags
        if labels is not UNSET:
            field_dict["labels"] = labels
        if job_template_id is not UNSET:
            field_dict["job_template_id"] = job_template_id
        if job_template_name is not UNSET:
            field_dict["job_template_name"] = job_template_name
        if job_credentials is not UNSET:
            field_dict["job_credentials"] = job_credentials
        if credential_names is not UNSET:
            field_dict["credentialNames"] = credential_names
        if verbosity is not UNSET:
            field_dict["verbosity"] = verbosity
        if job_type is not UNSET:
            field_dict["job_type"] = job_type
        if forks is not UNSET:
            field_dict["forks"] = forks
        if job_slicing is not UNSET:
            field_dict["job_slicing"] = job_slicing
        if diff_mode is not UNSET:
            field_dict["diff_mode"] = diff_mode
        if execution_environment is not UNSET:
            field_dict["execution_environment"] = execution_environment
        if instance_group_id is not UNSET:
            field_dict["instance_group_id"] = instance_group_id
        if instance_group_name is not UNSET:
            field_dict["instance_group_name"] = instance_group_name

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.aap_job_template_executor_parameters_extra_vars import AAPJobTemplateExecutorParametersExtraVars

        d = dict(src_dict)

        def _parse_credential_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        credential_id = _parse_credential_id(d.pop("credential_id", UNSET))

        def _parse_integration_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        integration_id = _parse_integration_id(d.pop("integration_id", UNSET))

        def _parse_organization_id(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        organization_id = _parse_organization_id(d.pop("organizationId", UNSET))

        def _parse_organization_name(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        organization_name = _parse_organization_name(d.pop("organization_name", UNSET))

        def _parse_inventory_id(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        inventory_id = _parse_inventory_id(d.pop("inventory_id", UNSET))

        def _parse_inventory_name(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        inventory_name = _parse_inventory_name(d.pop("inventory_name", UNSET))

        _extra_vars = d.pop("extra_vars", UNSET)
        extra_vars: AAPJobTemplateExecutorParametersExtraVars | Unset
        if isinstance(_extra_vars, Unset):
            extra_vars = UNSET
        else:
            extra_vars = AAPJobTemplateExecutorParametersExtraVars.from_dict(_extra_vars)

        def _parse_limit(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        limit = _parse_limit(d.pop("limit", UNSET))

        def _parse_tags(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        tags = _parse_tags(d.pop("tags", UNSET))

        def _parse_skip_tags(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        skip_tags = _parse_skip_tags(d.pop("skip_tags", UNSET))

        def _parse_labels(data: object) -> list[str] | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                labels_type_0 = cast(list[str], data)

                return labels_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[str] | None | Unset, data)

        labels = _parse_labels(d.pop("labels", UNSET))

        def _parse_job_template_id(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        job_template_id = _parse_job_template_id(d.pop("job_template_id", UNSET))

        def _parse_job_template_name(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        job_template_name = _parse_job_template_name(d.pop("job_template_name", UNSET))

        def _parse_job_credentials(data: object) -> list[int] | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                job_credentials_type_0 = cast(list[int], data)

                return job_credentials_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[int] | None | Unset, data)

        job_credentials = _parse_job_credentials(d.pop("job_credentials", UNSET))

        def _parse_credential_names(data: object) -> list[str] | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                credential_names_type_0 = cast(list[str], data)

                return credential_names_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[str] | None | Unset, data)

        credential_names = _parse_credential_names(d.pop("credentialNames", UNSET))

        _verbosity = d.pop("verbosity", UNSET)
        verbosity: AAPVerbosity | Unset
        if isinstance(_verbosity, Unset):
            verbosity = UNSET
        else:
            verbosity = AAPVerbosity(_verbosity)

        def _parse_job_type(data: object) -> AAPJobType | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                job_type_type_0 = AAPJobType(data)

                return job_type_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(AAPJobType | None | Unset, data)

        job_type = _parse_job_type(d.pop("job_type", UNSET))

        def _parse_forks(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        forks = _parse_forks(d.pop("forks", UNSET))

        def _parse_job_slicing(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        job_slicing = _parse_job_slicing(d.pop("job_slicing", UNSET))

        def _parse_diff_mode(data: object) -> bool | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(bool | None | Unset, data)

        diff_mode = _parse_diff_mode(d.pop("diff_mode", UNSET))

        def _parse_execution_environment(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        execution_environment = _parse_execution_environment(d.pop("execution_environment", UNSET))

        def _parse_instance_group_id(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        instance_group_id = _parse_instance_group_id(d.pop("instance_group_id", UNSET))

        def _parse_instance_group_name(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        instance_group_name = _parse_instance_group_name(d.pop("instance_group_name", UNSET))

        aap_job_template_executor_parameters = cls(
            credential_id=credential_id,
            integration_id=integration_id,
            organization_id=organization_id,
            organization_name=organization_name,
            inventory_id=inventory_id,
            inventory_name=inventory_name,
            extra_vars=extra_vars,
            limit=limit,
            tags=tags,
            skip_tags=skip_tags,
            labels=labels,
            job_template_id=job_template_id,
            job_template_name=job_template_name,
            job_credentials=job_credentials,
            credential_names=credential_names,
            verbosity=verbosity,
            job_type=job_type,
            forks=forks,
            job_slicing=job_slicing,
            diff_mode=diff_mode,
            execution_environment=execution_environment,
            instance_group_id=instance_group_id,
            instance_group_name=instance_group_name,
        )

        aap_job_template_executor_parameters.additional_properties = d
        return aap_job_template_executor_parameters

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
