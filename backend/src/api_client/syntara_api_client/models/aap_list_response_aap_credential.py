from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define

if TYPE_CHECKING:
    from ..models.aap_credential import AAPCredential


T = TypeVar("T", bound="AAPListResponseAAPCredential")


@_attrs_define
class AAPListResponseAAPCredential:
    """
    Attributes:
        count (int):
        results (list[AAPCredential]):
    """

    count: int
    results: list[AAPCredential]

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
        from ..models.aap_credential import AAPCredential

        d = dict(src_dict)
        count = d.pop("count")

        results = []
        _results = d.pop("results")
        for results_item_data in _results:
            results_item = AAPCredential.from_dict(results_item_data)

            results.append(results_item)

        aap_list_response_aap_credential = cls(
            count=count,
            results=results,
        )

        return aap_list_response_aap_credential
