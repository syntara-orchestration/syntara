"""Resolve Form Prompt callbacks against persisted submissions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import structlog
from sqlmodel import select

from syntara.core.models.user import User
from syntara.forms.models.api_models import FormPromptStatus
from syntara.forms.models.form_prompt import FormPrompt

if TYPE_CHECKING:
    from uuid import UUID

    from sqlmodel.ext.asyncio.session import AsyncSession

logger = structlog.stdlib.get_logger(__name__)


@dataclass(frozen=True)
class NotFormPromptSignal:
    """The callback ID does not identify a persisted Form Prompt."""


@dataclass(frozen=True)
class RejectedFormPromptSignal:
    """A Form Prompt callback has no usable persisted submission."""

    reason: str


@dataclass(frozen=True)
class VerifiedFormPromptSignal:
    """A Form Prompt callback backed by its persisted submission."""

    payload: dict[str, Any]


FormPromptSignalResolution = NotFormPromptSignal | RejectedFormPromptSignal | VerifiedFormPromptSignal


def build_form_prompt_signal_payload(
    prompt: FormPrompt,
    *,
    responded_by_username: str | None,
) -> dict[str, Any]:
    """Build the stable workflow output payload from a persisted Form Prompt."""
    return {
        "outcome": "submitted",
        "response_data": prompt.response_data,
        "responded_by": responded_by_username,
        "responded_at": prompt.responded_at.isoformat() if prompt.responded_at is not None else None,
        "prompt_id": str(prompt.id),
    }


async def resolve_verified_form_prompt_signal(
    session: AsyncSession,
    execution_id: UUID,
    temporal_activity_id: str,
) -> FormPromptSignalResolution:
    """Resolve a callback ID to its authoritative Form Prompt submission.

    No matching row means the callback belongs to another activity type. A
    matching row is guarded: it must be uniquely identified and contain a
    complete persisted submission before the workflow can be resumed.
    """
    result = await session.exec(
        select(FormPrompt)
        .where(FormPrompt.execution_id == execution_id)
        .where(FormPrompt.temporal_activity_id == temporal_activity_id)
        .limit(2)
    )
    prompts = result.all()

    if not prompts:
        return NotFormPromptSignal()
    if len(prompts) > 1:
        logger.error(
            "Ambiguous Form Prompt callback target",
            execution_id=execution_id,
            temporal_activity_id=temporal_activity_id,
            matching_prompt_count=len(prompts),
        )
        return RejectedFormPromptSignal(reason="multiple matching prompts")

    prompt = prompts[0]
    if prompt.status != FormPromptStatus.SUBMITTED:
        return RejectedFormPromptSignal(reason=f"prompt status is {prompt.status.value}")
    if prompt.response_data is None or prompt.responded_at is None:
        return RejectedFormPromptSignal(reason="submitted prompt has incomplete response data")

    responded_by_username: str | None = None
    if prompt.responded_by is not None:
        responder = await session.get(User, prompt.responded_by)
        if responder is not None:
            responded_by_username = responder.username

    return VerifiedFormPromptSignal(
        payload=build_form_prompt_signal_payload(
            prompt,
            responded_by_username=responded_by_username,
        )
    )
