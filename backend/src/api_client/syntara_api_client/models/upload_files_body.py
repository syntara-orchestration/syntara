from __future__ import annotations

from collections.abc import Mapping
from io import BytesIO
from typing import Any, TypeVar
from uuid import UUID

from attrs import define as _attrs_define

from .. import types
from ..types import File

T = TypeVar("T", bound="UploadFilesBody")


@_attrs_define
class UploadFilesBody:
    """Request body for POST /files endpoint.

    Attributes:
        files (list[File]): Files to upload (1-10 files, max 10MB each)
        project_id (UUID): Project to associate files with
    """

    files: list[File]
    project_id: UUID

    def to_dict(self) -> dict[str, Any]:
        files = []
        for files_item_data in self.files:
            files_item = files_item_data.to_tuple()

            files.append(files_item)

        project_id = str(self.project_id)

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "files": files,
                "project_id": project_id,
            }
        )

        return field_dict

    def to_multipart(self) -> types.RequestFiles:
        files: types.RequestFiles = []

        for files_item_element in self.files:
            files.append(("files", files_item_element.to_tuple()))

        files.append(("project_id", (None, str(self.project_id).encode(), "text/plain")))

        return files

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        files = []
        _files = d.pop("files")
        for files_item_data in _files:
            files_item = File(payload=BytesIO(files_item_data))

            files.append(files_item)

        project_id = UUID(d.pop("project_id"))

        upload_files_body = cls(
            files=files,
            project_id=project_id,
        )

        return upload_files_body
