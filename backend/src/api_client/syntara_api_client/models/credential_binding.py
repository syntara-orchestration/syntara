from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="CredentialBinding")


@_attrs_define
class CredentialBinding:
    """Recipe-to-credential mapping for a workflow node.

    Attributes:
        credential_recipe_id (str): Qualified credential recipe identifier requested by the workload.
        credential_ref (UUID): Syntara credential selected for the credential recipe.
    """

    credential_recipe_id: str
    credential_ref: UUID
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        credential_recipe_id = self.credential_recipe_id

        credential_ref = str(self.credential_ref)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "credential_recipe_id": credential_recipe_id,
                "credential_ref": credential_ref,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        credential_recipe_id = d.pop("credential_recipe_id")

        credential_ref = UUID(d.pop("credential_ref"))

        credential_binding = cls(
            credential_recipe_id=credential_recipe_id,
            credential_ref=credential_ref,
        )

        credential_binding.additional_properties = d
        return credential_binding

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
