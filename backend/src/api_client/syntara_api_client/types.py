"""Contains some shared types for properties"""

from collections.abc import MutableMapping
from http import HTTPStatus
from typing import BinaryIO, Generic, Literal, TypeVar

import httpx
from attrs import define


class Unset:
    def __bool__(self) -> Literal[False]:
        return False


UNSET: Unset = Unset()

FileJsonType = tuple[str | None, bytes | BinaryIO, str | None]


@define
class File:
    """Contains information for file uploads"""

    payload: BinaryIO
    file_name: str | None = None
    mime_type: str | None = None

    def to_tuple(self) -> FileJsonType:
        """Return a tuple representation that httpx will accept for multipart/form-data"""
        return self.file_name, self.payload, self.mime_type


FileTypes = File | FileJsonType | bytes | BinaryIO
RequestFiles = list[tuple[str, FileJsonType | bytes | BinaryIO]]


T = TypeVar("T")


class UnexpectedResponseException(Exception):
    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


@define
class BaseResponse:
    """Base response"""

    status_code: HTTPStatus
    is_success: bool
    content: bytes
    headers: MutableMapping[str, str]
    request: httpx.Request

    def assert_successful(self, message: str = "") -> None:
        if not message and self.request:
            message = f"Request {self.request.method} has failed with status {self.status_code}"
            if self.content:
                message += f", content: {self.content.decode()}"
        if not self.is_success:
            raise UnexpectedResponseException(message=message, status_code=int(self.status_code))

    def assert_error(self, message: str = "") -> None:
        if not message and self.request:
            message = (
                f"Request {self.request.method} was expected to fail, but was successful with status {self.status_code}"
            )
        if self.is_success:
            raise UnexpectedResponseException(message=message, status_code=int(self.status_code))


@define
class Response(BaseResponse, Generic[T]):
    """Response"""

    parsed: T | None

    def assert_and_get(self, message: str = "") -> T:
        self.assert_successful(message)

        if self.parsed is None:
            raise UnexpectedResponseException(message="Expected an object but received None")
        return self.parsed


__all__ = [
    "UNSET",
    "File",
    "FileJsonType",
    "FileTypes",
    "BaseResponse",
    "Response",
    "Unset",
    "UnexpectedResponseException",
]
