from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar
from uuid import UUID

from attrs import define as _attrs_define

if TYPE_CHECKING:
    from ..models.file_upload_info import FileUploadInfo


T = TypeVar("T", bound="FileUploadResponse")


@_attrs_define
class FileUploadResponse:
    """Response model for POST /api/v1/files endpoint.

    Attributes:
        file_ids (list[UUID]): List of file IDs for later reference in invocations
        files (list[FileUploadInfo]): Metadata for each uploaded file
    """

    file_ids: list[UUID]
    files: list[FileUploadInfo]

    def to_dict(self) -> dict[str, Any]:
        file_ids = []
        for file_ids_item_data in self.file_ids:
            file_ids_item = str(file_ids_item_data)
            file_ids.append(file_ids_item)

        files = []
        for files_item_data in self.files:
            files_item = files_item_data.to_dict()
            files.append(files_item)

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "file_ids": file_ids,
                "files": files,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.file_upload_info import FileUploadInfo

        d = dict(src_dict)
        file_ids = []
        _file_ids = d.pop("file_ids")
        for file_ids_item_data in _file_ids:
            file_ids_item = UUID(file_ids_item_data)

            file_ids.append(file_ids_item)

        files = []
        _files = d.pop("files")
        for files_item_data in _files:
            files_item = FileUploadInfo.from_dict(files_item_data)

            files.append(files_item)

        file_upload_response = cls(
            file_ids=file_ids,
            files=files,
        )

        return file_upload_response
