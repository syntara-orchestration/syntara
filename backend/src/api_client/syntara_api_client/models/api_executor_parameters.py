from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.http_method import HTTPMethod
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.api_executor_parameters_body_type_0 import APIExecutorParametersBodyType0
    from ..models.api_executor_parameters_headers import APIExecutorParametersHeaders
    from ..models.api_executor_parameters_query_params import APIExecutorParametersQueryParams


T = TypeVar("T", bound="APIExecutorParameters")


@_attrs_define
class APIExecutorParameters:
    """Parameters for API executor (http_request activity).

    Attributes:
        method (HTTPMethod): Supported HTTP methods for API requests.
        url (None | str | Unset): Request URL (optional when a Secret URL credential provides it)
        headers (APIExecutorParametersHeaders | Unset):
        body (APIExecutorParametersBodyType0 | None | str | Unset):
        query_params (APIExecutorParametersQueryParams | Unset):
        credential_id (None | str | Unset): Syntara credential UUID for authentication or Secret URL.
    """

    method: HTTPMethod
    url: None | str | Unset = UNSET
    headers: APIExecutorParametersHeaders | Unset = UNSET
    body: APIExecutorParametersBodyType0 | None | str | Unset = UNSET
    query_params: APIExecutorParametersQueryParams | Unset = UNSET
    credential_id: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.api_executor_parameters_body_type_0 import APIExecutorParametersBodyType0

        method = self.method.value

        url: None | str | Unset
        if isinstance(self.url, Unset):
            url = UNSET
        else:
            url = self.url

        headers: dict[str, Any] | Unset = UNSET
        if not isinstance(self.headers, Unset):
            headers = self.headers.to_dict()

        body: dict[str, Any] | None | str | Unset
        if isinstance(self.body, Unset):
            body = UNSET
        elif isinstance(self.body, APIExecutorParametersBodyType0):
            body = self.body.to_dict()
        else:
            body = self.body

        query_params: dict[str, Any] | Unset = UNSET
        if not isinstance(self.query_params, Unset):
            query_params = self.query_params.to_dict()

        credential_id: None | str | Unset
        if isinstance(self.credential_id, Unset):
            credential_id = UNSET
        else:
            credential_id = self.credential_id

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "method": method,
            }
        )
        if url is not UNSET:
            field_dict["url"] = url
        if headers is not UNSET:
            field_dict["headers"] = headers
        if body is not UNSET:
            field_dict["body"] = body
        if query_params is not UNSET:
            field_dict["query_params"] = query_params
        if credential_id is not UNSET:
            field_dict["credential_id"] = credential_id

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.api_executor_parameters_body_type_0 import APIExecutorParametersBodyType0
        from ..models.api_executor_parameters_headers import APIExecutorParametersHeaders
        from ..models.api_executor_parameters_query_params import APIExecutorParametersQueryParams

        d = dict(src_dict)
        method = HTTPMethod(d.pop("method"))

        def _parse_url(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        url = _parse_url(d.pop("url", UNSET))

        _headers = d.pop("headers", UNSET)
        headers: APIExecutorParametersHeaders | Unset
        if isinstance(_headers, Unset):
            headers = UNSET
        else:
            headers = APIExecutorParametersHeaders.from_dict(_headers)

        def _parse_body(data: object) -> APIExecutorParametersBodyType0 | None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                body_type_0 = APIExecutorParametersBodyType0.from_dict(data)

                return body_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(APIExecutorParametersBodyType0 | None | str | Unset, data)

        body = _parse_body(d.pop("body", UNSET))

        _query_params = d.pop("query_params", UNSET)
        query_params: APIExecutorParametersQueryParams | Unset
        if isinstance(_query_params, Unset):
            query_params = UNSET
        else:
            query_params = APIExecutorParametersQueryParams.from_dict(_query_params)

        def _parse_credential_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        credential_id = _parse_credential_id(d.pop("credential_id", UNSET))

        api_executor_parameters = cls(
            method=method,
            url=url,
            headers=headers,
            body=body,
            query_params=query_params,
            credential_id=credential_id,
        )

        api_executor_parameters.additional_properties = d
        return api_executor_parameters

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
