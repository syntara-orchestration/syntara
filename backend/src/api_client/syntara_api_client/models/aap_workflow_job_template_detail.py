from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.aap_summary_field import AAPSummaryField


T = TypeVar("T", bound="AAPWorkflowJobTemplateDetail")


@_attrs_define
class AAPWorkflowJobTemplateDetail:
    """Ansible Automation Platform workflow job template with prompt-on-launch capabilities and default values.

    Attributes:
        id (int):
        name (str):
        description (None | str | Unset):
        url (None | str | Unset): Link to the workflow template in Ansible Automation Platform Controller UI
        ask_inventory_on_launch (bool | Unset):  Default: False.
        ask_credential_on_launch (bool | Unset):  Default: False.
        ask_variables_on_launch (bool | Unset):  Default: False.
        ask_limit_on_launch (bool | Unset):  Default: False.
        ask_scm_branch_on_launch (bool | Unset):  Default: False.
        ask_labels_on_launch (bool | Unset):  Default: False.
        ask_tags_on_launch (bool | Unset):  Default: False.
        ask_skip_tags_on_launch (bool | Unset):  Default: False.
        survey_enabled (bool | Unset):  Default: False.
        default_inventory (AAPSummaryField | None | Unset): Default inventory from workflow template summary_fields
        default_labels (list[AAPSummaryField] | Unset): Default labels from workflow template summary_fields
        limit (None | str | Unset): Default limit pattern
        scm_branch (None | str | Unset): Default SCM branch
        job_tags (None | str | Unset): Default job tags
        skip_tags (None | str | Unset): Default skip tags
        extra_vars (None | str | Unset): Default extra variables (YAML format, max 1MB)
    """

    id: int
    name: str
    description: None | str | Unset = UNSET
    url: None | str | Unset = UNSET
    ask_inventory_on_launch: bool | Unset = False
    ask_credential_on_launch: bool | Unset = False
    ask_variables_on_launch: bool | Unset = False
    ask_limit_on_launch: bool | Unset = False
    ask_scm_branch_on_launch: bool | Unset = False
    ask_labels_on_launch: bool | Unset = False
    ask_tags_on_launch: bool | Unset = False
    ask_skip_tags_on_launch: bool | Unset = False
    survey_enabled: bool | Unset = False
    default_inventory: AAPSummaryField | None | Unset = UNSET
    default_labels: list[AAPSummaryField] | Unset = UNSET
    limit: None | str | Unset = UNSET
    scm_branch: None | str | Unset = UNSET
    job_tags: None | str | Unset = UNSET
    skip_tags: None | str | Unset = UNSET
    extra_vars: None | str | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        from ..models.aap_summary_field import AAPSummaryField

        id = self.id

        name = self.name

        description: None | str | Unset
        if isinstance(self.description, Unset):
            description = UNSET
        else:
            description = self.description

        url: None | str | Unset
        if isinstance(self.url, Unset):
            url = UNSET
        else:
            url = self.url

        ask_inventory_on_launch = self.ask_inventory_on_launch

        ask_credential_on_launch = self.ask_credential_on_launch

        ask_variables_on_launch = self.ask_variables_on_launch

        ask_limit_on_launch = self.ask_limit_on_launch

        ask_scm_branch_on_launch = self.ask_scm_branch_on_launch

        ask_labels_on_launch = self.ask_labels_on_launch

        ask_tags_on_launch = self.ask_tags_on_launch

        ask_skip_tags_on_launch = self.ask_skip_tags_on_launch

        survey_enabled = self.survey_enabled

        default_inventory: dict[str, Any] | None | Unset
        if isinstance(self.default_inventory, Unset):
            default_inventory = UNSET
        elif isinstance(self.default_inventory, AAPSummaryField):
            default_inventory = self.default_inventory.to_dict()
        else:
            default_inventory = self.default_inventory

        default_labels: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.default_labels, Unset):
            default_labels = []
            for default_labels_item_data in self.default_labels:
                default_labels_item = default_labels_item_data.to_dict()
                default_labels.append(default_labels_item)

        limit: None | str | Unset
        if isinstance(self.limit, Unset):
            limit = UNSET
        else:
            limit = self.limit

        scm_branch: None | str | Unset
        if isinstance(self.scm_branch, Unset):
            scm_branch = UNSET
        else:
            scm_branch = self.scm_branch

        job_tags: None | str | Unset
        if isinstance(self.job_tags, Unset):
            job_tags = UNSET
        else:
            job_tags = self.job_tags

        skip_tags: None | str | Unset
        if isinstance(self.skip_tags, Unset):
            skip_tags = UNSET
        else:
            skip_tags = self.skip_tags

        extra_vars: None | str | Unset
        if isinstance(self.extra_vars, Unset):
            extra_vars = UNSET
        else:
            extra_vars = self.extra_vars

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "id": id,
                "name": name,
            }
        )
        if description is not UNSET:
            field_dict["description"] = description
        if url is not UNSET:
            field_dict["url"] = url
        if ask_inventory_on_launch is not UNSET:
            field_dict["ask_inventory_on_launch"] = ask_inventory_on_launch
        if ask_credential_on_launch is not UNSET:
            field_dict["ask_credential_on_launch"] = ask_credential_on_launch
        if ask_variables_on_launch is not UNSET:
            field_dict["ask_variables_on_launch"] = ask_variables_on_launch
        if ask_limit_on_launch is not UNSET:
            field_dict["ask_limit_on_launch"] = ask_limit_on_launch
        if ask_scm_branch_on_launch is not UNSET:
            field_dict["ask_scm_branch_on_launch"] = ask_scm_branch_on_launch
        if ask_labels_on_launch is not UNSET:
            field_dict["ask_labels_on_launch"] = ask_labels_on_launch
        if ask_tags_on_launch is not UNSET:
            field_dict["ask_tags_on_launch"] = ask_tags_on_launch
        if ask_skip_tags_on_launch is not UNSET:
            field_dict["ask_skip_tags_on_launch"] = ask_skip_tags_on_launch
        if survey_enabled is not UNSET:
            field_dict["survey_enabled"] = survey_enabled
        if default_inventory is not UNSET:
            field_dict["default_inventory"] = default_inventory
        if default_labels is not UNSET:
            field_dict["default_labels"] = default_labels
        if limit is not UNSET:
            field_dict["limit"] = limit
        if scm_branch is not UNSET:
            field_dict["scm_branch"] = scm_branch
        if job_tags is not UNSET:
            field_dict["job_tags"] = job_tags
        if skip_tags is not UNSET:
            field_dict["skip_tags"] = skip_tags
        if extra_vars is not UNSET:
            field_dict["extra_vars"] = extra_vars

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.aap_summary_field import AAPSummaryField

        d = dict(src_dict)
        id = d.pop("id")

        name = d.pop("name")

        def _parse_description(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        description = _parse_description(d.pop("description", UNSET))

        def _parse_url(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        url = _parse_url(d.pop("url", UNSET))

        ask_inventory_on_launch = d.pop("ask_inventory_on_launch", UNSET)

        ask_credential_on_launch = d.pop("ask_credential_on_launch", UNSET)

        ask_variables_on_launch = d.pop("ask_variables_on_launch", UNSET)

        ask_limit_on_launch = d.pop("ask_limit_on_launch", UNSET)

        ask_scm_branch_on_launch = d.pop("ask_scm_branch_on_launch", UNSET)

        ask_labels_on_launch = d.pop("ask_labels_on_launch", UNSET)

        ask_tags_on_launch = d.pop("ask_tags_on_launch", UNSET)

        ask_skip_tags_on_launch = d.pop("ask_skip_tags_on_launch", UNSET)

        survey_enabled = d.pop("survey_enabled", UNSET)

        def _parse_default_inventory(data: object) -> AAPSummaryField | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                default_inventory_type_0 = AAPSummaryField.from_dict(data)

                return default_inventory_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(AAPSummaryField | None | Unset, data)

        default_inventory = _parse_default_inventory(d.pop("default_inventory", UNSET))

        _default_labels = d.pop("default_labels", UNSET)
        default_labels: list[AAPSummaryField] | Unset = UNSET
        if _default_labels is not UNSET:
            default_labels = []
            for default_labels_item_data in _default_labels:
                default_labels_item = AAPSummaryField.from_dict(default_labels_item_data)

                default_labels.append(default_labels_item)

        def _parse_limit(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        limit = _parse_limit(d.pop("limit", UNSET))

        def _parse_scm_branch(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        scm_branch = _parse_scm_branch(d.pop("scm_branch", UNSET))

        def _parse_job_tags(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        job_tags = _parse_job_tags(d.pop("job_tags", UNSET))

        def _parse_skip_tags(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        skip_tags = _parse_skip_tags(d.pop("skip_tags", UNSET))

        def _parse_extra_vars(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        extra_vars = _parse_extra_vars(d.pop("extra_vars", UNSET))

        aap_workflow_job_template_detail = cls(
            id=id,
            name=name,
            description=description,
            url=url,
            ask_inventory_on_launch=ask_inventory_on_launch,
            ask_credential_on_launch=ask_credential_on_launch,
            ask_variables_on_launch=ask_variables_on_launch,
            ask_limit_on_launch=ask_limit_on_launch,
            ask_scm_branch_on_launch=ask_scm_branch_on_launch,
            ask_labels_on_launch=ask_labels_on_launch,
            ask_tags_on_launch=ask_tags_on_launch,
            ask_skip_tags_on_launch=ask_skip_tags_on_launch,
            survey_enabled=survey_enabled,
            default_inventory=default_inventory,
            default_labels=default_labels,
            limit=limit,
            scm_branch=scm_branch,
            job_tags=job_tags,
            skip_tags=skip_tags,
            extra_vars=extra_vars,
        )

        return aap_workflow_job_template_detail
