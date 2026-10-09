from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define

if TYPE_CHECKING:
    from ..models.aap_workflow_job_template import AAPWorkflowJobTemplate


T = TypeVar("T", bound="AAPListResponseAAPWorkflowJobTemplate")


@_attrs_define
class AAPListResponseAAPWorkflowJobTemplate:
    """
    Attributes:
        count (int):
        results (list[AAPWorkflowJobTemplate]):
    """

    count: int
    results: list[AAPWorkflowJobTemplate]

    def to_dict(self) -> dict[str, Any]:
        count = self.count

        results = []
        for results_item_data in self.results:
            results_item = results_item_data.to_dict()
            results.append(results_item)

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "count": count,
                "results": results,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.aap_workflow_job_template import AAPWorkflowJobTemplate

        d = dict(src_dict)
        count = d.pop("count")

        results = []
        _results = d.pop("results")
        for results_item_data in _results:
            results_item = AAPWorkflowJobTemplate.from_dict(results_item_data)

            results.append(results_item)

        aap_list_response_aap_workflow_job_template = cls(
            count=count,
            results=results,
        )

        return aap_list_response_aap_workflow_job_template
