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


def collect_direct_loop_bodies(
    loop_bodies: Mapping[str, set[str]],
    loop_ids: set[str],
) -> dict[str, set[str]]:
    """Keep each loop's direct body nodes and remove nested-loop descendants.

    A nested loop controller remains in its parent's direct body. Nodes inside
    that controller's body do not, so a parent-loop probe cannot use a nested
    descendant as evidence for the parent's current iteration.
    """
    direct_bodies: dict[str, set[str]] = {}
    for loop_id, body in loop_bodies.items():
        nested_descendants = set().union(*(loop_bodies.get(node_id, set()) for node_id in body if node_id in loop_ids))
        direct_bodies[loop_id] = body - nested_descendants
    return direct_bodies
