from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define

from ..models.file_storage_status import FileStorageStatus

T = TypeVar("T", bound="FileStorageStatusResponse")


@_attrs_define
class FileStorageStatusResponse:
    """Response model for GET /files/storage_status endpoint.

    Attributes:
        status (FileStorageStatus): Availability of the S3-compatible object storage backend.
    """

    status: FileStorageStatus

    def to_dict(self) -> dict[str, Any]:
        status = self.status.value

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "status": status,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        status = FileStorageStatus(d.pop("status"))

        file_storage_status_response = cls(
            status=status,
        )

        return file_storage_status_response
