from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.aap_workflow_job_template_executor_parameters_extra_vars import (
        AAPWorkflowJobTemplateExecutorParametersExtraVars,
    )


T = TypeVar("T", bound="AAPWorkflowJobTemplateExecutorParameters")


@_attrs_define
class AAPWorkflowJobTemplateExecutorParameters:
    """Parameters for Ansible Automation Platform Workflow Job Template executor.

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
            extra_vars (AAPWorkflowJobTemplateExecutorParametersExtraVars | Unset): Extra variables to pass to job/workflow
                job
            limit (None | str | Unset): Limit job execution to specific hosts
            tags (None | str | Unset): Ansible tags to run (comma-separated)
            skip_tags (None | str | Unset): Ansible tags to skip (comma-separated)
            labels (list[str] | None | Unset): Ansible Automation Platform label names to append to template's default
                labels. Names are resolved to IDs at launch time. New labels that don't exist in Ansible Automation Platform
                will be created automatically. Note: Labels are APPENDED to template defaults, not replaced.
            workflow_job_template_id (int | None | Unset): Ansible Automation Platform workflow job template ID to launch
            workflow_job_template_name (None | str | Unset): Ansible Automation Platform workflow job template name (used
                with organization_name)
            scm_branch (None | str | Unset): SCM branch override for projects in workflow
    """

    credential_id: None | str | Unset = UNSET
    integration_id: None | str | Unset = UNSET
    organization_id: int | None | Unset = UNSET
    organization_name: None | str | Unset = UNSET
    inventory_id: int | None | Unset = UNSET
    inventory_name: None | str | Unset = UNSET
    extra_vars: AAPWorkflowJobTemplateExecutorParametersExtraVars | Unset = UNSET
    limit: None | str | Unset = UNSET
    tags: None | str | Unset = UNSET
    skip_tags: None | str | Unset = UNSET
    labels: list[str] | None | Unset = UNSET
    workflow_job_template_id: int | None | Unset = UNSET
    workflow_job_template_name: None | str | Unset = UNSET
    scm_branch: None | str | Unset = UNSET
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

        workflow_job_template_id: int | None | Unset
        if isinstance(self.workflow_job_template_id, Unset):
            workflow_job_template_id = UNSET
        else:
            workflow_job_template_id = self.workflow_job_template_id

        workflow_job_template_name: None | str | Unset
        if isinstance(self.workflow_job_template_name, Unset):
            workflow_job_template_name = UNSET
        else:
            workflow_job_template_name = self.workflow_job_template_name

        scm_branch: None | str | Unset
        if isinstance(self.scm_branch, Unset):
            scm_branch = UNSET
        else:
            scm_branch = self.scm_branch

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
        if workflow_job_template_id is not UNSET:
            field_dict["workflow_job_template_id"] = workflow_job_template_id
        if workflow_job_template_name is not UNSET:
            field_dict["workflow_job_template_name"] = workflow_job_template_name
        if scm_branch is not UNSET:
            field_dict["scm_branch"] = scm_branch

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.aap_workflow_job_template_executor_parameters_extra_vars import (
            AAPWorkflowJobTemplateExecutorParametersExtraVars,
        )

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
        extra_vars: AAPWorkflowJobTemplateExecutorParametersExtraVars | Unset
        if isinstance(_extra_vars, Unset):
            extra_vars = UNSET
        else:
            extra_vars = AAPWorkflowJobTemplateExecutorParametersExtraVars.from_dict(_extra_vars)

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

        def _parse_workflow_job_template_id(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        workflow_job_template_id = _parse_workflow_job_template_id(d.pop("workflow_job_template_id", UNSET))

        def _parse_workflow_job_template_name(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        workflow_job_template_name = _parse_workflow_job_template_name(d.pop("workflow_job_template_name", UNSET))

        def _parse_scm_branch(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        scm_branch = _parse_scm_branch(d.pop("scm_branch", UNSET))

        aap_workflow_job_template_executor_parameters = cls(
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
            workflow_job_template_id=workflow_job_template_id,
            workflow_job_template_name=workflow_job_template_name,
            scm_branch=scm_branch,
        )

        aap_workflow_job_template_executor_parameters.additional_properties = d
        return aap_workflow_job_template_executor_parameters

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
