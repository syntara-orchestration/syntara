from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.file_status import FileStatus
from ..types import UNSET, Unset

T = TypeVar("T", bound="FileUploadInfo")


@_attrs_define
class FileUploadInfo:
    """Response model for individual file upload information.

    Security Note:
        file_path is intentionally excluded from this model to prevent
        exposing internal filesystem paths in API responses.

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
            is_project_deleted (bool | None | Unset): True when the owning project has been soft-deleted; the file is
                retained as an orphan. Null when not computed (e.g. upload response).
    """

    file_id: UUID
    filename: str
    size_bytes: int
    mime_type: str
    status: FileStatus
    is_project_deleted: bool | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        file_id = str(self.file_id)

        filename = self.filename

        size_bytes = self.size_bytes

        mime_type = self.mime_type

        status = self.status.value

        is_project_deleted: bool | None | Unset
        if isinstance(self.is_project_deleted, Unset):
            is_project_deleted = UNSET
        else:
            is_project_deleted = self.is_project_deleted

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "file_id": file_id,
                "filename": filename,
                "size_bytes": size_bytes,
                "mime_type": mime_type,
                "status": status,
            }
        )
        if is_project_deleted is not UNSET:
            field_dict["is_project_deleted"] = is_project_deleted

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        file_id = UUID(d.pop("file_id"))

        filename = d.pop("filename")

        size_bytes = d.pop("size_bytes")

        mime_type = d.pop("mime_type")

        status = FileStatus(d.pop("status"))

        def _parse_is_project_deleted(data: object) -> bool | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(bool | None | Unset, data)

        is_project_deleted = _parse_is_project_deleted(d.pop("is_project_deleted", UNSET))

        file_upload_info = cls(
            file_id=file_id,
            filename=filename,
            size_bytes=size_bytes,
            mime_type=mime_type,
            status=status,
            is_project_deleted=is_project_deleted,
        )

        file_upload_info.additional_properties = d
        return file_upload_info

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
