"""Pure loop-body traversal shared by definition validation and execution."""

from collections.abc import Mapping, Sequence


def collect_loop_bodies(
    adjacency: Mapping[str, Sequence[str]],
    iterate_successors: Mapping[str, Sequence[str]],
) -> dict[str, set[str]]:
    """Walk each loop independently using adjacency with feedback edges removed.

    Only the seed edges use the iterate port. Interior edges may have no port.
    Keeping visited sets per loop preserves membership when bodies overlap.
    """
    bodies: dict[str, set[str]] = {}
    for loop_id, seeds in iterate_successors.items():
        body: set[str] = set()
        pending = list(seeds)
        while pending:
            node_id = pending.pop()
            if node_id == loop_id or node_id in body:
                continue
            body.add(node_id)
            pending.extend(adjacency.get(node_id, ()))
        bodies[loop_id] = body
    return bodies
