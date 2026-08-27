from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.error_data import ErrorData
from ...models.kpi_dashboard import KPIDashboard
from ...types import Response


def _get_kwargs() -> dict[str, Any]:
    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/_internal/metrics/kpis",
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> ErrorData | KPIDashboard | None:
    if response.status_code == 200:
        response_200 = KPIDashboard.from_dict(response.json())

        return response_200

    if response.status_code == 400:
        response_400 = ErrorData.from_dict(response.json())

        return response_400

    if response.status_code == 401:
        response_401 = ErrorData.from_dict(response.json())

        return response_401

    if response.status_code == 403:
        response_403 = ErrorData.from_dict(response.json())

        return response_403

    if response.status_code == 404:
        response_404 = ErrorData.from_dict(response.json())

        return response_404

    if response.status_code == 409:
        response_409 = ErrorData.from_dict(response.json())

        return response_409

    if response.status_code == 422:
        response_422 = ErrorData.from_dict(response.json())

        return response_422

    if response.status_code == 429:
        response_429 = ErrorData.from_dict(response.json())

        return response_429

    if response.status_code == 500:
        response_500 = ErrorData.from_dict(response.json())

        return response_500

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Response[ErrorData | KPIDashboard]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
        request=response.request,
        is_success=response.is_success,
    )


def sync_detailed(
    *,
    client: AuthenticatedClient | Client,
) -> Response[ErrorData | KPIDashboard]:
    """Metrics store KPIs

     Return a computed KPI dashboard covering all Orchestrator components.

    Maps metrics to the KPIs defined in the Orchestrator KPI documents:
    - Orchestrator Key Performance Indicators (KPIs)
    - Orchestrator LLM/Agent Performance KPIs

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorData | KPIDashboard]
    """

    kwargs = _get_kwargs()

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient | Client,
) -> ErrorData | KPIDashboard | None:
    """Metrics store KPIs

     Return a computed KPI dashboard covering all Orchestrator components.

    Maps metrics to the KPIs defined in the Orchestrator KPI documents:
    - Orchestrator Key Performance Indicators (KPIs)
    - Orchestrator LLM/Agent Performance KPIs

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ErrorData | KPIDashboard
    """

    return sync_detailed(
        client=client,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient | Client,
) -> Response[ErrorData | KPIDashboard]:
    """Metrics store KPIs

     Return a computed KPI dashboard covering all Orchestrator components.

    Maps metrics to the KPIs defined in the Orchestrator KPI documents:
    - Orchestrator Key Performance Indicators (KPIs)
    - Orchestrator LLM/Agent Performance KPIs

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorData | KPIDashboard]
    """

    kwargs = _get_kwargs()

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient | Client,
) -> ErrorData | KPIDashboard | None:
    """Metrics store KPIs

     Return a computed KPI dashboard covering all Orchestrator components.

    Maps metrics to the KPIs defined in the Orchestrator KPI documents:
    - Orchestrator Key Performance Indicators (KPIs)
    - Orchestrator LLM/Agent Performance KPIs

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ErrorData | KPIDashboard
    """

    return (
        await asyncio_detailed(
            client=client,
        )
    ).parsed
