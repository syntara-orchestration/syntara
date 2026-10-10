from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define

if TYPE_CHECKING:
    from ..models.file_upload_info import FileUploadInfo


T = TypeVar("T", bound="FilesMetadataResponse")


@_attrs_define
class FilesMetadataResponse:
    """Response model for GET /files/metadata endpoint.

    Attributes:
        files (list[FileUploadInfo]): Metadata for each found file (missing IDs are silently omitted)
    """

    files: list[FileUploadInfo]

    def to_dict(self) -> dict[str, Any]:
        files = []
        for files_item_data in self.files:
            files_item = files_item_data.to_dict()
            files.append(files_item)

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "files": files,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.file_upload_info import FileUploadInfo

        d = dict(src_dict)
        files = []
        _files = d.pop("files")
        for files_item_data in _files:
            files_item = FileUploadInfo.from_dict(files_item_data)

            files.append(files_item)

        files_metadata_response = cls(
            files=files,
        )

        return files_metadata_response
