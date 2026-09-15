from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.file_status import FileStatus
from ..types import UNSET, Unset

T = TypeVar("T", bound="FileDetailResponse")


@_attrs_define
class FileDetailResponse:
    """Response model for GET /api/v1/files/{file_id} endpoint.

    Attributes:
        file_id (UUID): Unique file identifier (UUID)
        filename (str): Original filename from upload
        size_bytes (int): File size in bytes
        mime_type (str): Detected MIME type of the file
        status (FileStatus): Status enum for file conversion lifecycle.

            States:
                PENDING_CONVERSION: File uploaded, waiting for conversion
                CONVERTING: Conversion in progress
                CONVERTED: Successfully converted to text/markdown
                CONVERSION_FAILED: Conversion failed with error
        is_project_deleted (bool): True when the owning project has been soft-deleted; the file is retained as an
            orphan. Project-scoped files:delete cannot remove orphans after soft-delete; only system-scope files:delete with
            a known file UUID can.
        conversion_error (None | str | Unset): Error message if conversion failed
    """

    file_id: UUID
    filename: str
    size_bytes: int
    mime_type: str
    status: FileStatus
    is_project_deleted: bool
    conversion_error: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        file_id = str(self.file_id)

        filename = self.filename

        size_bytes = self.size_bytes

        mime_type = self.mime_type

        status = self.status.value

        is_project_deleted = self.is_project_deleted

        conversion_error: None | str | Unset
        if isinstance(self.conversion_error, Unset):
            conversion_error = UNSET
        else:
            conversion_error = self.conversion_error

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "file_id": file_id,
                "filename": filename,
                "size_bytes": size_bytes,
                "mime_type": mime_type,
                "status": status,
                "is_project_deleted": is_project_deleted,
            }
        )
        if conversion_error is not UNSET:
            field_dict["conversion_error"] = conversion_error

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        file_id = UUID(d.pop("file_id"))

        filename = d.pop("filename")

        size_bytes = d.pop("size_bytes")

        mime_type = d.pop("mime_type")

        status = FileStatus(d.pop("status"))

        is_project_deleted = d.pop("is_project_deleted")

        def _parse_conversion_error(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        conversion_error = _parse_conversion_error(d.pop("conversion_error", UNSET))

        file_detail_response = cls(
            file_id=file_id,
            filename=filename,
            size_bytes=size_bytes,
            mime_type=mime_type,
            status=status,
            is_project_deleted=is_project_deleted,
            conversion_error=conversion_error,
        )

        file_detail_response.additional_properties = d
        return file_detail_response

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
