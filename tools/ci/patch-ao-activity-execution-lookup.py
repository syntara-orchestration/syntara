#!/usr/bin/env python3
"""Retry AO ActivityExecution lookup until monitoring creates the row.

The syntara checkout deployed by this pipeline (feat/ANSTRAT-1803 plus
credential.resolve) looks up ActivityExecution.id as the EP work_item_id
and fails the script node with a non-retryable ContextError when the row
is missing. Hello-world nodes have maximum_attempts=1, so Temporal does
not retry.

Activity rows are created by register_activity_monitoring, which the workflow
interceptor starts in the background. The script activity can run first
(especially with two myao-worker replicas). This patch waits for the row
instead of failing the node.

Applied to the AO image via install-syntara-from-src during Konflux e2e.
Remove once AO retries this lookup itself.
"""

from __future__ import annotations

import argparse
import base64
from pathlib import Path

TARGET = Path(
    "/opt/app-root/src/src/syntara/workflows/workflow_engine/activities/ep/ep_dispatch_activity.py"
)

OLD = '''async def _lookup_activity_execution_id(execution_id: uuid.UUID, temporal_activity_id: str) -> uuid.UUID:
    """Look up ActivityExecution.id by execution_id and temporal_activity_id."""
    async with AsyncSessionLocal() as session:
        row = (
            await session.exec(
                select(ActivityExecution)
                .where(ActivityExecution.execution_id == execution_id)
                .where(ActivityExecution.temporal_activity_id == temporal_activity_id)
            )
        ).first()
    if row is None:
        msg = f"ActivityExecution not found for execution_id={execution_id} activity_id={temporal_activity_id}"
        raise ApplicationError(msg, type="ContextError", non_retryable=True)
    return row.id
'''

NEW = '''async def _lookup_activity_execution_id(execution_id: uuid.UUID, temporal_activity_id: str) -> uuid.UUID:
    """Look up ActivityExecution.id by execution_id and temporal_activity_id.

    Activity rows are created by register_activity_monitoring after the
    Execution record exists. Script dispatch can start first; retry until
    the row is present instead of failing the node as a ContextError.
    Konflux overlay: tools/ci/patch-ao-activity-execution-lookup.py
    """
    deadline = asyncio.get_running_loop().time() + 20.0
    delay = 0.05
    while True:
        async with AsyncSessionLocal() as session:
            row = (
                await session.exec(
                    select(ActivityExecution)
                    .where(ActivityExecution.execution_id == execution_id)
                    .where(ActivityExecution.temporal_activity_id == temporal_activity_id)
                )
            ).first()
        if row is not None:
            return row.id
        remaining = deadline - asyncio.get_running_loop().time()
        if remaining <= 0:
            msg = f"ActivityExecution not found for execution_id={execution_id} activity_id={temporal_activity_id}"
            raise ApplicationError(msg, type="ContextError", non_retryable=True)
        await asyncio.sleep(min(delay, remaining))
        delay = min(delay * 2, 1.0)
'''

MARKER = "Konflux overlay: tools/ci/patch-ao-activity-execution-lookup.py"


def patch(path: Path) -> str:
    text = path.read_text()
    if MARKER in text:
        return "ActivityExecution lookup retry already patched"
    if OLD not in text:
        raise SystemExit(
            f"{path}: _lookup_activity_execution_id changed; update "
            "tools/ci/patch-ao-activity-execution-lookup.py"
        )
    path.write_text(text.replace(OLD, NEW, 1))
    return "patched ActivityExecution lookup to retry until monitoring creates the row"


def install_overlay(fragment: Path, patch_script: Path) -> str:
    """Append a RUN that applies this script after syntara is copied into the AO image."""
    b64 = base64.b64encode(patch_script.read_bytes()).decode("ascii")
    run = (
        "# patch-ao-activity-execution-lookup.py\n"
        f"RUN printf '%s' '{b64}' | base64 -d | python3\n"
    )
    text = fragment.read_text()
    if "patch-ao-activity-execution-lookup.py" in text:
        return "ActivityExecution lookup patch already in overlay"
    if "USER 1001" not in text:
        raise SystemExit(f"USER 1001 not found in {fragment}")
    fragment.write_text(text.replace("USER 1001", run + "USER 1001", 1))
    return "installed ActivityExecution lookup retry into AO overlay"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "path",
        nargs="?",
        type=Path,
        default=TARGET,
        help="ep_dispatch_activity.py to patch (default: path inside the AO image)",
    )
    parser.add_argument(
        "--install-overlay",
        type=Path,
        metavar="FRAGMENT",
        help="insert a RUN into install-syntara-from-src that applies this script",
    )
    args = parser.parse_args()
    if args.install_overlay is not None:
        print(install_overlay(args.install_overlay, Path(__file__).resolve()))
        return
    print(patch(args.path))


if __name__ == "__main__":
    main()
