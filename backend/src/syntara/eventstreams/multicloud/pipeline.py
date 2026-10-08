"""Transport-neutral listener core: decode -> filter -> hand off. This is what HOLDS.

There is no fixed message schema: whatever arrives is decoded to an opaque mapping,
run through a cheap filter in the listener node, and — if it passes — handed off *as a
whole* to Temporal (fan-out to N workflows). Because we never know the payload shape,
there is nothing to validate into a typed model, so FastStream's headline consume-side
feature (parse-from-annotation into a Pydantic model) contributes nothing here. What is
left is three steps that are genuinely identical across Kafka / AWS / Azure and are
therefore written ONCE, here:

    decode_message(raw)     -> dict[str, Any]   # opaque; shape unknown
    passes_filter(decoded)  -> bool             # cheap predicate in the listener node
    hand_off_to_workflow(decoded, ...)          # pass the WHOLE decoded message to Temporal

The ONLY thing that stays per-transport is getting ``raw`` bytes out of the broker's
message object and turning success/failure into that transport's ack / redelivery call
— see ``brokers/*``. Everything above the byte boundary is shared.
"""

from __future__ import annotations

import json
from typing import Any

import structlog

logger = structlog.stdlib.get_logger(__name__)

# Fan-out target(s): a single passing message may start several workflows, each
# receiving the WHOLE decoded message unchanged. Deterministic ids (below) keep
# at-least-once redeliveries idempotent — Temporal rejects a duplicate start.
_TARGET_WORKFLOWS: tuple[str, ...] = ("onboarding-workflow",)

# The filter is schema-agnostic on purpose: we do not know the payload shape, so the
# predicate may only look at whatever happens to be present. Swap this constant / the
# predicate body for the real routing rule. Keeping it here (not per broker) is the
# whole point — the filter is transport-neutral and written once.
_REQUIRED_KEYS: frozenset[str] = frozenset({"event_type"})


class DecodeError(ValueError):
    """Raised when a raw message cannot be decoded — a CONTENT error, not transient.

    Content errors can never succeed on retry, so each broker handler translates this
    into an ack-and-drop (never block the partition), distinct from a transient
    hand-off failure which is nacked/redelivered.
    """


def decode_message(raw: bytes) -> dict[str, Any]:
    """Decode raw bytes into an opaque mapping. No schema is assumed or validated.

    We only require that the payload is a JSON object so downstream steps have keys to
    inspect; the *values* and their meaning are unknown and passed through untouched.
    """
    try:
        decoded = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        msg = "message body is not valid JSON"
        raise DecodeError(msg) from exc
    if not isinstance(decoded, dict):
        msg = f"decoded message is {type(decoded).__name__}, expected a JSON object"
        raise DecodeError(msg)
    return decoded


def passes_filter(decoded: dict[str, Any]) -> bool:
    """Cheap predicate run in the listener node; only passing messages are handed off."""
    return _REQUIRED_KEYS.issubset(decoded.keys())


async def hand_off_to_workflow(
    decoded: dict[str, Any],
    *,
    db: Any,
    log: Any,
    transport: str,
    message_id: str,
) -> None:
    """Hand the WHOLE decoded message off to Temporal, fanning out to every target.

    The payload is forwarded verbatim — the workflow, not this listener, owns any
    interpretation of the (unknown) schema. Deterministic workflow ids derived from
    ``message_id`` make redeliveries idempotent. Stub: no real Temporal client is
    wired here (kept out of scope), only the hand-off shape is shown.
    """
    for workflow in _TARGET_WORKFLOWS:
        workflow_id = f"eventstream-{message_id}-{workflow}"
        # await temporal_client.start_workflow(workflow, decoded, id=workflow_id, ...)
        log.info(
            "workflow_handoff",
            transport=transport,
            message_id=message_id,
            workflow=workflow,
            workflow_id=workflow_id,
            payload_keys=sorted(decoded.keys()),
            db_bound=bool(db),
        )
