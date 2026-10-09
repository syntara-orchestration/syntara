from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define

from ..models.aap_job_type import AAPJobType
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.aap_summary_field import AAPSummaryField


T = TypeVar("T", bound="AAPJobTemplateDetail")


@_attrs_define
class AAPJobTemplateDetail:
    """Ansible Automation Platform job template with prompt-on-launch capabilities and default values.

    Attributes:
        id (int):
        name (str):
        description (None | str | Unset):
        url (None | str | Unset): Link to the job template in Ansible Automation Platform Controller UI
        ask_job_type_on_launch (bool | Unset):  Default: False.
        ask_inventory_on_launch (bool | Unset):  Default: False.
        ask_credential_on_launch (bool | Unset):  Default: False.
        ask_variables_on_launch (bool | Unset):  Default: False.
        ask_limit_on_launch (bool | Unset):  Default: False.
        ask_tags_on_launch (bool | Unset):  Default: False.
        ask_skip_tags_on_launch (bool | Unset):  Default: False.
        ask_verbosity_on_launch (bool | Unset):  Default: False.
        ask_diff_mode_on_launch (bool | Unset):  Default: False.
        ask_forks_on_launch (bool | Unset):  Default: False.
        ask_job_slice_count_on_launch (bool | Unset):  Default: False.
        ask_execution_environment_on_launch (bool | Unset):  Default: False.
        ask_instance_groups_on_launch (bool | Unset):  Default: False.
        ask_labels_on_launch (bool | Unset):  Default: False.
        ask_timeout_on_launch (bool | Unset):  Default: False.
        ask_scm_branch_on_launch (bool | Unset):  Default: False.
        survey_enabled (bool | Unset):  Default: False.
        default_inventory (AAPSummaryField | None | Unset): Default inventory from job template summary_fields
        default_execution_environment (AAPSummaryField | None | Unset): Default execution environment from job template
            summary_fields
        default_credentials (list[AAPSummaryField] | Unset): Default credentials from job template summary_fields
        default_labels (list[AAPSummaryField] | Unset): Default labels from job template summary_fields
        job_type (AAPJobType | None | Unset): Default job type - "run" or "check"
        verbosity (int | None | Unset): Default verbosity level (0-5)
        forks (int | None | Unset): Default number of forks (max 10,000)
        limit (None | str | Unset): Default limit pattern
        job_tags (None | str | Unset): Default job tags
        skip_tags (None | str | Unset): Default skip tags
        diff_mode (bool | None | Unset): Default diff mode setting
        job_slice_count (int | None | Unset): Default job slice count (max 10,000)
        timeout (int | None | Unset): Default timeout in seconds (max 7 days)
        extra_vars (None | str | Unset): Default extra variables (YAML format, max 1MB)
    """

    id: int
    name: str
    description: None | str | Unset = UNSET
    url: None | str | Unset = UNSET
    ask_job_type_on_launch: bool | Unset = False
    ask_inventory_on_launch: bool | Unset = False
    ask_credential_on_launch: bool | Unset = False
    ask_variables_on_launch: bool | Unset = False
    ask_limit_on_launch: bool | Unset = False
    ask_tags_on_launch: bool | Unset = False
    ask_skip_tags_on_launch: bool | Unset = False
    ask_verbosity_on_launch: bool | Unset = False
    ask_diff_mode_on_launch: bool | Unset = False
    ask_forks_on_launch: bool | Unset = False
    ask_job_slice_count_on_launch: bool | Unset = False
    ask_execution_environment_on_launch: bool | Unset = False
    ask_instance_groups_on_launch: bool | Unset = False
    ask_labels_on_launch: bool | Unset = False
    ask_timeout_on_launch: bool | Unset = False
    ask_scm_branch_on_launch: bool | Unset = False
    survey_enabled: bool | Unset = False
    default_inventory: AAPSummaryField | None | Unset = UNSET
    default_execution_environment: AAPSummaryField | None | Unset = UNSET
    default_credentials: list[AAPSummaryField] | Unset = UNSET
    default_labels: list[AAPSummaryField] | Unset = UNSET
    job_type: AAPJobType | None | Unset = UNSET
    verbosity: int | None | Unset = UNSET
    forks: int | None | Unset = UNSET
    limit: None | str | Unset = UNSET
    job_tags: None | str | Unset = UNSET
    skip_tags: None | str | Unset = UNSET
    diff_mode: bool | None | Unset = UNSET
    job_slice_count: int | None | Unset = UNSET
    timeout: int | None | Unset = UNSET
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

        ask_job_type_on_launch = self.ask_job_type_on_launch

        ask_inventory_on_launch = self.ask_inventory_on_launch

        ask_credential_on_launch = self.ask_credential_on_launch

        ask_variables_on_launch = self.ask_variables_on_launch

        ask_limit_on_launch = self.ask_limit_on_launch

        ask_tags_on_launch = self.ask_tags_on_launch

        ask_skip_tags_on_launch = self.ask_skip_tags_on_launch

        ask_verbosity_on_launch = self.ask_verbosity_on_launch

        ask_diff_mode_on_launch = self.ask_diff_mode_on_launch

        ask_forks_on_launch = self.ask_forks_on_launch

        ask_job_slice_count_on_launch = self.ask_job_slice_count_on_launch

        ask_execution_environment_on_launch = self.ask_execution_environment_on_launch

        ask_instance_groups_on_launch = self.ask_instance_groups_on_launch

        ask_labels_on_launch = self.ask_labels_on_launch

        ask_timeout_on_launch = self.ask_timeout_on_launch

        ask_scm_branch_on_launch = self.ask_scm_branch_on_launch

        survey_enabled = self.survey_enabled

        default_inventory: dict[str, Any] | None | Unset
        if isinstance(self.default_inventory, Unset):
            default_inventory = UNSET
        elif isinstance(self.default_inventory, AAPSummaryField):
            default_inventory = self.default_inventory.to_dict()
        else:
            default_inventory = self.default_inventory

        default_execution_environment: dict[str, Any] | None | Unset
        if isinstance(self.default_execution_environment, Unset):
            default_execution_environment = UNSET
        elif isinstance(self.default_execution_environment, AAPSummaryField):
            default_execution_environment = self.default_execution_environment.to_dict()
        else:
            default_execution_environment = self.default_execution_environment

        default_credentials: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.default_credentials, Unset):
            default_credentials = []
            for default_credentials_item_data in self.default_credentials:
                default_credentials_item = default_credentials_item_data.to_dict()
                default_credentials.append(default_credentials_item)

        default_labels: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.default_labels, Unset):
            default_labels = []
            for default_labels_item_data in self.default_labels:
                default_labels_item = default_labels_item_data.to_dict()
                default_labels.append(default_labels_item)

        job_type: None | str | Unset
        if isinstance(self.job_type, Unset):
            job_type = UNSET
        elif isinstance(self.job_type, AAPJobType):
            job_type = self.job_type.value
        else:
            job_type = self.job_type

        verbosity: int | None | Unset
        if isinstance(self.verbosity, Unset):
            verbosity = UNSET
        else:
            verbosity = self.verbosity

        forks: int | None | Unset
        if isinstance(self.forks, Unset):
            forks = UNSET
        else:
            forks = self.forks

        limit: None | str | Unset
        if isinstance(self.limit, Unset):
            limit = UNSET
        else:
            limit = self.limit

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

        diff_mode: bool | None | Unset
        if isinstance(self.diff_mode, Unset):
            diff_mode = UNSET
        else:
            diff_mode = self.diff_mode

        job_slice_count: int | None | Unset
        if isinstance(self.job_slice_count, Unset):
            job_slice_count = UNSET
        else:
            job_slice_count = self.job_slice_count

        timeout: int | None | Unset
        if isinstance(self.timeout, Unset):
            timeout = UNSET
        else:
            timeout = self.timeout

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
        if ask_job_type_on_launch is not UNSET:
            field_dict["ask_job_type_on_launch"] = ask_job_type_on_launch
        if ask_inventory_on_launch is not UNSET:
            field_dict["ask_inventory_on_launch"] = ask_inventory_on_launch
        if ask_credential_on_launch is not UNSET:
            field_dict["ask_credential_on_launch"] = ask_credential_on_launch
        if ask_variables_on_launch is not UNSET:
            field_dict["ask_variables_on_launch"] = ask_variables_on_launch
        if ask_limit_on_launch is not UNSET:
            field_dict["ask_limit_on_launch"] = ask_limit_on_launch
        if ask_tags_on_launch is not UNSET:
            field_dict["ask_tags_on_launch"] = ask_tags_on_launch
        if ask_skip_tags_on_launch is not UNSET:
            field_dict["ask_skip_tags_on_launch"] = ask_skip_tags_on_launch
        if ask_verbosity_on_launch is not UNSET:
            field_dict["ask_verbosity_on_launch"] = ask_verbosity_on_launch
        if ask_diff_mode_on_launch is not UNSET:
            field_dict["ask_diff_mode_on_launch"] = ask_diff_mode_on_launch
        if ask_forks_on_launch is not UNSET:
            field_dict["ask_forks_on_launch"] = ask_forks_on_launch
        if ask_job_slice_count_on_launch is not UNSET:
            field_dict["ask_job_slice_count_on_launch"] = ask_job_slice_count_on_launch
        if ask_execution_environment_on_launch is not UNSET:
            field_dict["ask_execution_environment_on_launch"] = ask_execution_environment_on_launch
        if ask_instance_groups_on_launch is not UNSET:
            field_dict["ask_instance_groups_on_launch"] = ask_instance_groups_on_launch
        if ask_labels_on_launch is not UNSET:
            field_dict["ask_labels_on_launch"] = ask_labels_on_launch
        if ask_timeout_on_launch is not UNSET:
            field_dict["ask_timeout_on_launch"] = ask_timeout_on_launch
        if ask_scm_branch_on_launch is not UNSET:
            field_dict["ask_scm_branch_on_launch"] = ask_scm_branch_on_launch
        if survey_enabled is not UNSET:
            field_dict["survey_enabled"] = survey_enabled
        if default_inventory is not UNSET:
            field_dict["default_inventory"] = default_inventory
        if default_execution_environment is not UNSET:
            field_dict["default_execution_environment"] = default_execution_environment
        if default_credentials is not UNSET:
            field_dict["default_credentials"] = default_credentials
        if default_labels is not UNSET:
            field_dict["default_labels"] = default_labels
        if job_type is not UNSET:
            field_dict["job_type"] = job_type
        if verbosity is not UNSET:
            field_dict["verbosity"] = verbosity
        if forks is not UNSET:
            field_dict["forks"] = forks
        if limit is not UNSET:
            field_dict["limit"] = limit
        if job_tags is not UNSET:
            field_dict["job_tags"] = job_tags
        if skip_tags is not UNSET:
            field_dict["skip_tags"] = skip_tags
        if diff_mode is not UNSET:
            field_dict["diff_mode"] = diff_mode
        if job_slice_count is not UNSET:
            field_dict["job_slice_count"] = job_slice_count
        if timeout is not UNSET:
            field_dict["timeout"] = timeout
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

        ask_job_type_on_launch = d.pop("ask_job_type_on_launch", UNSET)

        ask_inventory_on_launch = d.pop("ask_inventory_on_launch", UNSET)

        ask_credential_on_launch = d.pop("ask_credential_on_launch", UNSET)

        ask_variables_on_launch = d.pop("ask_variables_on_launch", UNSET)

        ask_limit_on_launch = d.pop("ask_limit_on_launch", UNSET)

        ask_tags_on_launch = d.pop("ask_tags_on_launch", UNSET)

        ask_skip_tags_on_launch = d.pop("ask_skip_tags_on_launch", UNSET)

        ask_verbosity_on_launch = d.pop("ask_verbosity_on_launch", UNSET)

        ask_diff_mode_on_launch = d.pop("ask_diff_mode_on_launch", UNSET)

        ask_forks_on_launch = d.pop("ask_forks_on_launch", UNSET)

        ask_job_slice_count_on_launch = d.pop("ask_job_slice_count_on_launch", UNSET)

        ask_execution_environment_on_launch = d.pop("ask_execution_environment_on_launch", UNSET)

        ask_instance_groups_on_launch = d.pop("ask_instance_groups_on_launch", UNSET)

        ask_labels_on_launch = d.pop("ask_labels_on_launch", UNSET)

        ask_timeout_on_launch = d.pop("ask_timeout_on_launch", UNSET)

        ask_scm_branch_on_launch = d.pop("ask_scm_branch_on_launch", UNSET)

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

        def _parse_default_execution_environment(data: object) -> AAPSummaryField | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                default_execution_environment_type_0 = AAPSummaryField.from_dict(data)

                return default_execution_environment_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(AAPSummaryField | None | Unset, data)

        default_execution_environment = _parse_default_execution_environment(
            d.pop("default_execution_environment", UNSET)
        )

        _default_credentials = d.pop("default_credentials", UNSET)
        default_credentials: list[AAPSummaryField] | Unset = UNSET
        if _default_credentials is not UNSET:
            default_credentials = []
            for default_credentials_item_data in _default_credentials:
                default_credentials_item = AAPSummaryField.from_dict(default_credentials_item_data)

                default_credentials.append(default_credentials_item)

        _default_labels = d.pop("default_labels", UNSET)
        default_labels: list[AAPSummaryField] | Unset = UNSET
        if _default_labels is not UNSET:
            default_labels = []
            for default_labels_item_data in _default_labels:
                default_labels_item = AAPSummaryField.from_dict(default_labels_item_data)

                default_labels.append(default_labels_item)

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

        def _parse_verbosity(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        verbosity = _parse_verbosity(d.pop("verbosity", UNSET))

        def _parse_forks(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        forks = _parse_forks(d.pop("forks", UNSET))

        def _parse_limit(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        limit = _parse_limit(d.pop("limit", UNSET))

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

        def _parse_diff_mode(data: object) -> bool | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(bool | None | Unset, data)

        diff_mode = _parse_diff_mode(d.pop("diff_mode", UNSET))

        def _parse_job_slice_count(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        job_slice_count = _parse_job_slice_count(d.pop("job_slice_count", UNSET))

        def _parse_timeout(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        timeout = _parse_timeout(d.pop("timeout", UNSET))

        def _parse_extra_vars(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        extra_vars = _parse_extra_vars(d.pop("extra_vars", UNSET))

        aap_job_template_detail = cls(
            id=id,
            name=name,
            description=description,
            url=url,
            ask_job_type_on_launch=ask_job_type_on_launch,
            ask_inventory_on_launch=ask_inventory_on_launch,
            ask_credential_on_launch=ask_credential_on_launch,
            ask_variables_on_launch=ask_variables_on_launch,
            ask_limit_on_launch=ask_limit_on_launch,
            ask_tags_on_launch=ask_tags_on_launch,
            ask_skip_tags_on_launch=ask_skip_tags_on_launch,
            ask_verbosity_on_launch=ask_verbosity_on_launch,
            ask_diff_mode_on_launch=ask_diff_mode_on_launch,
            ask_forks_on_launch=ask_forks_on_launch,
            ask_job_slice_count_on_launch=ask_job_slice_count_on_launch,
            ask_execution_environment_on_launch=ask_execution_environment_on_launch,
            ask_instance_groups_on_launch=ask_instance_groups_on_launch,
            ask_labels_on_launch=ask_labels_on_launch,
            ask_timeout_on_launch=ask_timeout_on_launch,
            ask_scm_branch_on_launch=ask_scm_branch_on_launch,
            survey_enabled=survey_enabled,
            default_inventory=default_inventory,
            default_execution_environment=default_execution_environment,
            default_credentials=default_credentials,
            default_labels=default_labels,
            job_type=job_type,
            verbosity=verbosity,
            forks=forks,
            limit=limit,
            job_tags=job_tags,
            skip_tags=skip_tags,
            diff_mode=diff_mode,
            job_slice_count=job_slice_count,
            timeout=timeout,
            extra_vars=extra_vars,
        )

        return aap_job_template_detail
