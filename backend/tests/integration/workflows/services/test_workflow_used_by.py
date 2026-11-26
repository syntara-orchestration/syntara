"""Used-By reverse-reference query (DB-backed).

Exercises ``WorkflowService.list_published_parents`` against the real alembic-built schema: it
counts distinct published parents whose published version references a child via a sub_workflow
node, excludes draft-only references, counts a parent once regardless of how many sub_workflow
nodes it has, reflects republishes, and filters the returned parent details by the caller's
allowed projects while keeping the total count unfiltered.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

import pytest

from syntara.authz.engine import AllowedProjectsResult
from syntara.authz.models.project import Project
from syntara.workflows.models import Workflow, WorkflowVersion
from syntara.workflows.services.workflow_service import WorkflowService

if TYPE_CHECKING:
    from sqlmodel.ext.asyncio.session import AsyncSession

    from syntara.core.models import User

_ALL_PROJECTS = AllowedProjectsResult(all_projects=True, project_ids=[])


def _ref_node(child_id: UUID, index: int) -> dict[str, Any]:
    return {
        "id": f"sub_{index}",
        "type": "sub_workflow",
        "parameters": {"workflow_id": str(child_id), "trigger_node_id": "child_trigger", "input_mapping": {}},
    }


def _definition(nodes: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": "2.0.0",
        "triggers": [{"id": "trigger", "type": "manual_trigger", "parameters": {}}],
        "nodes": nodes,
        "edges": [],
    }


def _referencing_def(child_id: UUID, node_count: int = 1) -> dict[str, Any]:
    return _definition([_ref_node(child_id, i) for i in range(node_count)])


def _plain_def() -> dict[str, Any]:
    return _definition([{"id": "s", "type": "script", "parameters": {"language": "bash", "code": "echo hi"}}])


async def _publish(
    session: AsyncSession, *, created_by: UUID, project_id: UUID, definition: dict[str, Any], name: str
) -> UUID:
    """Create a published workflow (is_enabled + published_version_id, per the DB constraint)."""
    workflow_id = uuid4()
    session.add(Workflow(id=workflow_id, name=name, created_by=created_by, project_id=project_id))
    await session.flush()
    version_id = uuid4()
    session.add(
        WorkflowVersion(
            id=version_id,
            workflow_id=workflow_id,
            version=1,
            schema_version="2.0.0",
            workflow_definition=definition,
            created_by=created_by,
        )
    )
    await session.flush()
    workflow = await session.get(Workflow, workflow_id)
    assert workflow is not None
    workflow.is_enabled = True
    workflow.published_version_id = version_id
    await session.commit()
    return workflow_id


async def _draft(
    session: AsyncSession, *, created_by: UUID, project_id: UUID, definition: dict[str, Any], name: str
) -> UUID:
    """Create a draft workflow (no published version; is_enabled stays False per the DB constraint)."""
    workflow_id = uuid4()
    session.add(Workflow(id=workflow_id, name=name, created_by=created_by, project_id=project_id))
    await session.flush()
    session.add(
        WorkflowVersion(
            id=uuid4(),
            workflow_id=workflow_id,
            version=1,
            schema_version="2.0.0",
            workflow_definition=definition,
            created_by=created_by,
        )
    )
    await session.commit()
    return workflow_id


@pytest.mark.integration
@pytest.mark.asyncio
async def test_counts_published_parents_excludes_drafts_and_dedupes(
    test_db_session: AsyncSession, test_user: User, test_project_id: UUID
) -> None:
    """Published referencing parents are counted once each; drafts and non-referencing parents are not."""
    child_id = uuid4()
    service = WorkflowService(test_db_session, test_user)
    a = await _publish(
        test_db_session,
        created_by=test_user.id,
        project_id=test_project_id,
        definition=_referencing_def(child_id, 1),
        name=f"A-{uuid4().hex[:8]}",
    )
    b = await _publish(
        test_db_session,
        created_by=test_user.id,
        project_id=test_project_id,
        definition=_referencing_def(child_id, 3),
        name=f"B-{uuid4().hex[:8]}",
    )
    await _draft(
        test_db_session,
        created_by=test_user.id,
        project_id=test_project_id,
        definition=_referencing_def(child_id, 1),
        name=f"draft-{uuid4().hex[:8]}",
    )
    await _publish(
        test_db_session,
        created_by=test_user.id,
        project_id=test_project_id,
        definition=_plain_def(),
        name=f"noref-{uuid4().hex[:8]}",
    )

    result = await service.list_published_parents(child_id, allowed_projects=_ALL_PROJECTS)

    assert result.referencing_parent_count == 2
    ids = [r.id for r in result.resources]
    assert set(ids) == {a, b}
    assert ids.count(b) == 1  # three sub_workflow nodes, still one row


@pytest.mark.integration
@pytest.mark.asyncio
async def test_self_reference_is_counted(test_db_session: AsyncSession, test_user: User, test_project_id: UUID) -> None:
    """A workflow whose published version references itself appears in its own Used-By."""
    service = WorkflowService(test_db_session, test_user)
    self_id = uuid4()
    test_db_session.add(
        Workflow(id=self_id, name=f"self-{uuid4().hex[:8]}", created_by=test_user.id, project_id=test_project_id)
    )
    await test_db_session.flush()
    version_id = uuid4()
    test_db_session.add(
        WorkflowVersion(
            id=version_id,
            workflow_id=self_id,
            version=1,
            schema_version="2.0.0",
            workflow_definition=_referencing_def(self_id, 1),
            created_by=test_user.id,
        )
    )
    await test_db_session.flush()
    workflow = await test_db_session.get(Workflow, self_id)
    assert workflow is not None
    workflow.is_enabled = True
    workflow.published_version_id = version_id
    await test_db_session.commit()

    result = await service.list_published_parents(self_id, allowed_projects=_ALL_PROJECTS)

    assert result.referencing_parent_count >= 1
    assert self_id in {r.id for r in result.resources}


@pytest.mark.integration
@pytest.mark.asyncio
async def test_rbac_filters_items_but_not_total_count(
    test_db_session: AsyncSession, test_user: User, test_project_id: UUID
) -> None:
    """referencing_parent_count spans all projects; the items and their metadata are limited to allowed projects."""
    service = WorkflowService(test_db_session, test_user)
    child_id = uuid4()
    other = Project(name=f"other-{uuid4().hex[:8]}", created_by=test_user.id)
    test_db_session.add(other)
    await test_db_session.commit()

    visible = await _publish(
        test_db_session,
        created_by=test_user.id,
        project_id=test_project_id,
        definition=_referencing_def(child_id),
        name=f"vis-{uuid4().hex[:8]}",
    )
    hidden = await _publish(
        test_db_session,
        created_by=test_user.id,
        project_id=other.id,
        definition=_referencing_def(child_id),
        name=f"hidden-{uuid4().hex[:8]}",
    )

    allowed = AllowedProjectsResult(all_projects=False, project_ids=[test_project_id])
    result = await service.list_published_parents(child_id, allowed_projects=allowed)

    assert result.referencing_parent_count == 2  # both projects counted
    ids = {r.id for r in result.resources}
    assert ids == {visible}
    assert hidden not in ids
    # no metadata leak: the hidden parent's name is not disclosed
    hidden_workflow = await test_db_session.get(Workflow, hidden)
    assert hidden_workflow is not None
    assert hidden_workflow.name not in {r.name for r in result.resources}


@pytest.mark.integration
@pytest.mark.asyncio
async def test_rbac_none_visible_hides_all_items_keeps_total(
    test_db_session: AsyncSession, test_user: User, test_project_id: UUID
) -> None:
    """A caller allowed no projects sees an empty items list but the full referencing_parent_count."""
    service = WorkflowService(test_db_session, test_user)
    child_id = uuid4()
    await _publish(
        test_db_session,
        created_by=test_user.id,
        project_id=test_project_id,
        definition=_referencing_def(child_id),
        name=f"p-{uuid4().hex[:8]}",
    )

    allowed = AllowedProjectsResult(all_projects=False, project_ids=[])
    result = await service.list_published_parents(child_id, allowed_projects=allowed)

    assert result.referencing_parent_count == 1
    assert result.resources == []


@pytest.mark.integration
@pytest.mark.asyncio
async def test_republish_reflects_reference_change(
    test_db_session: AsyncSession, test_user: User, test_project_id: UUID
) -> None:
    """Repointing a parent's published version to a non-referencing version drops it from Used-By."""
    service = WorkflowService(test_db_session, test_user)
    child_id = uuid4()
    parent_id = await _publish(
        test_db_session,
        created_by=test_user.id,
        project_id=test_project_id,
        definition=_referencing_def(child_id),
        name=f"parent-{uuid4().hex[:8]}",
    )
    before = await service.list_published_parents(child_id, allowed_projects=_ALL_PROJECTS)
    assert before.referencing_parent_count == 1

    # Republish to a new version that no longer references the child.
    new_version_id = uuid4()
    test_db_session.add(
        WorkflowVersion(
            id=new_version_id,
            workflow_id=parent_id,
            version=2,
            schema_version="2.0.0",
            workflow_definition=_plain_def(),
            created_by=test_user.id,
        )
    )
    await test_db_session.flush()
    parent = await test_db_session.get(Workflow, parent_id)
    assert parent is not None
    parent.published_version_id = new_version_id
    await test_db_session.commit()

    after = await service.list_published_parents(child_id, allowed_projects=_ALL_PROJECTS)
    assert after.referencing_parent_count == 0
    assert after.resources == []


@pytest.mark.integration
@pytest.mark.asyncio
async def test_deleted_parent_is_excluded(
    test_db_session: AsyncSession, test_user: User, test_project_id: UUID
) -> None:
    """A hard-deleted parent (workflows are hard-deleted, versions cascade) drops out of Used-By."""
    service = WorkflowService(test_db_session, test_user)
    child_id = uuid4()
    parent_id = await _publish(
        test_db_session,
        created_by=test_user.id,
        project_id=test_project_id,
        definition=_referencing_def(child_id),
        name=f"parent-{uuid4().hex[:8]}",
    )
    assert (
        await service.list_published_parents(child_id, allowed_projects=_ALL_PROJECTS)
    ).referencing_parent_count == 1

    workflow = await test_db_session.get(Workflow, parent_id)
    assert workflow is not None
    await test_db_session.delete(workflow)
    await test_db_session.commit()

    after = await service.list_published_parents(child_id, allowed_projects=_ALL_PROJECTS)
    assert after.referencing_parent_count == 0
    assert after.resources == []
    assert await service.get_referencing_published_parent_ids(child_id) == []


@pytest.mark.integration
@pytest.mark.asyncio
async def test_referencing_parent_ids_are_unfiltered(
    test_db_session: AsyncSession, test_user: User, test_project_id: UUID
) -> None:
    """The internal id list returns every referencing published parent, across all projects."""
    service = WorkflowService(test_db_session, test_user)
    child_id = uuid4()
    other = Project(name=f"other-{uuid4().hex[:8]}", created_by=test_user.id)
    test_db_session.add(other)
    await test_db_session.commit()

    here = await _publish(
        test_db_session,
        created_by=test_user.id,
        project_id=test_project_id,
        definition=_referencing_def(child_id),
        name=f"here-{uuid4().hex[:8]}",
    )
    elsewhere = await _publish(
        test_db_session,
        created_by=test_user.id,
        project_id=other.id,
        definition=_referencing_def(child_id),
        name=f"elsewhere-{uuid4().hex[:8]}",
    )

    ids = await service.get_referencing_published_parent_ids(child_id)

    assert set(ids) == {here, elsewhere}


def _ref_node_trigger(child_id: UUID, trigger_node_id: str, index: int = 0) -> dict[str, Any]:
    return {
        "id": f"sub_{index}",
        "type": "sub_workflow",
        "parameters": {"workflow_id": str(child_id), "trigger_node_id": trigger_node_id, "input_mapping": {}},
    }


@pytest.mark.integration
@pytest.mark.asyncio
async def test_trigger_node_id_filters_to_specific_trigger(
    test_db_session: AsyncSession, test_user: User, test_project_id: UUID
) -> None:
    """With trigger_node_id set, only parents invoking that specific child trigger are returned."""
    service = WorkflowService(test_db_session, test_user)
    child_id = uuid4()
    parent_a = await _publish(
        test_db_session,
        created_by=test_user.id,
        project_id=test_project_id,
        definition=_definition([_ref_node_trigger(child_id, "trig_a")]),
        name=f"pa-{uuid4().hex[:8]}",
    )
    parent_b = await _publish(
        test_db_session,
        created_by=test_user.id,
        project_id=test_project_id,
        definition=_definition([_ref_node_trigger(child_id, "trig_b")]),
        name=f"pb-{uuid4().hex[:8]}",
    )

    unfiltered = await service.list_published_parents(child_id, allowed_projects=_ALL_PROJECTS)
    assert unfiltered.referencing_parent_count == 2
    assert {r.id for r in unfiltered.resources} == {parent_a, parent_b}

    only_a = await service.list_published_parents(child_id, trigger_node_ids=["trig_a"], allowed_projects=_ALL_PROJECTS)
    assert only_a.referencing_parent_count == 1
    assert {r.id for r in only_a.resources} == {parent_a}
    assert parent_b not in {r.id for r in only_a.resources}


@pytest.mark.integration
@pytest.mark.asyncio
async def test_count_published_parents_batch_returns_totals(
    test_db_session: AsyncSession, test_user: User, test_project_id: UUID
) -> None:
    """Batch counts return the unfiltered total per requested workflow, including zero."""
    service = WorkflowService(test_db_session, test_user)
    child_a = await _publish(
        test_db_session,
        created_by=test_user.id,
        project_id=test_project_id,
        definition=_plain_def(),
        name=f"ca-{uuid4().hex[:8]}",
    )
    child_b = await _publish(
        test_db_session,
        created_by=test_user.id,
        project_id=test_project_id,
        definition=_plain_def(),
        name=f"cb-{uuid4().hex[:8]}",
    )
    child_c = await _publish(
        test_db_session,
        created_by=test_user.id,
        project_id=test_project_id,
        definition=_plain_def(),
        name=f"cc-{uuid4().hex[:8]}",
    )
    for _ in range(2):
        await _publish(
            test_db_session,
            created_by=test_user.id,
            project_id=test_project_id,
            definition=_referencing_def(child_a),
            name=f"pa-{uuid4().hex[:8]}",
        )
    await _publish(
        test_db_session,
        created_by=test_user.id,
        project_id=test_project_id,
        definition=_referencing_def(child_b),
        name=f"pb-{uuid4().hex[:8]}",
    )

    result = await service.count_published_parents_batch([child_a, child_b, child_c], allowed_projects=_ALL_PROJECTS)
    by_id = {c.workflow_id: c.referencing_parent_count for c in result.counts}
    assert by_id == {child_a: 2, child_b: 1, child_c: 0}


@pytest.mark.integration
@pytest.mark.asyncio
async def test_count_published_parents_batch_omits_workflows_outside_visibility(
    test_db_session: AsyncSession, test_user: User, test_project_id: UUID
) -> None:
    """Batch counts omit workflows the caller cannot read, so counts cannot be probed for them."""
    service = WorkflowService(test_db_session, test_user)
    other = Project(name=f"other-{uuid4().hex[:8]}", created_by=test_user.id)
    test_db_session.add(other)
    await test_db_session.commit()

    here_child = await _publish(
        test_db_session,
        created_by=test_user.id,
        project_id=test_project_id,
        definition=_plain_def(),
        name=f"here-{uuid4().hex[:8]}",
    )
    hidden_child = await _publish(
        test_db_session,
        created_by=test_user.id,
        project_id=other.id,
        definition=_plain_def(),
        name=f"hidden-{uuid4().hex[:8]}",
    )
    await _publish(
        test_db_session,
        created_by=test_user.id,
        project_id=test_project_id,
        definition=_referencing_def(here_child),
        name=f"ph-{uuid4().hex[:8]}",
    )
    await _publish(
        test_db_session,
        created_by=test_user.id,
        project_id=other.id,
        definition=_referencing_def(hidden_child),
        name=f"phid-{uuid4().hex[:8]}",
    )

    allowed = AllowedProjectsResult(all_projects=False, project_ids=[test_project_id])
    result = await service.count_published_parents_batch([here_child, hidden_child], allowed_projects=allowed)
    by_id = {c.workflow_id: c.referencing_parent_count for c in result.counts}
    assert by_id.get(here_child) == 1
    assert hidden_child not in by_id


@pytest.mark.integration
@pytest.mark.asyncio
async def test_batch_count_matches_single_count_helper(
    test_db_session: AsyncSession, test_user: User, test_project_id: UUID
) -> None:
    """The batch raw-SQL aggregate and the single count helper agree on every child.

    Pins the two Used-By count implementations -- the ORM containment predicate behind
    ``count_referencing_published_parents`` and the raw-SQL unnest in ``count_published_parents_batch``
    -- so they cannot drift on published-only, distinctness, or node matching. The fixture covers a
    parent with two sub_workflow nodes to the same child (counted once), a draft-only reference
    (excluded), a published non-sub_workflow node that happens to carry a ``workflow_id`` param
    (excluded), and a cross-project published parent (included, since the count ignores visibility).
    """
    service = WorkflowService(test_db_session, test_user)
    other = Project(name=f"other-{uuid4().hex[:8]}", created_by=test_user.id)
    test_db_session.add(other)
    await test_db_session.commit()

    # The target child must exist as a readable workflow for the batch path to return its count.
    child = await _publish(
        test_db_session,
        created_by=test_user.id,
        project_id=test_project_id,
        definition=_plain_def(),
        name=f"child-{uuid4().hex[:8]}",
    )

    # (1) one published parent with TWO sub_workflow nodes to the same child -> counts once
    await _publish(
        test_db_session,
        created_by=test_user.id,
        project_id=test_project_id,
        definition=_referencing_def(child, node_count=2),
        name=f"dup-{uuid4().hex[:8]}",
    )
    # (2) a draft-only reference -> excluded (no published version)
    await _draft(
        test_db_session,
        created_by=test_user.id,
        project_id=test_project_id,
        definition=_referencing_def(child, 1),
        name=f"draft-{uuid4().hex[:8]}",
    )
    # (3) a published non-sub_workflow node carrying a workflow_id param -> excluded
    await _publish(
        test_db_session,
        created_by=test_user.id,
        project_id=test_project_id,
        definition=_definition(
            [{"id": "notsub", "type": "script", "parameters": {"workflow_id": str(child), "code": "echo hi"}}]
        ),
        name=f"nonsub-{uuid4().hex[:8]}",
    )
    # (4) a cross-project published parent -> included (count is unfiltered by visibility)
    await _publish(
        test_db_session,
        created_by=test_user.id,
        project_id=other.id,
        definition=_referencing_def(child, 1),
        name=f"xproj-{uuid4().hex[:8]}",
    )

    single = await service.count_referencing_published_parents(child)
    batch = await service.count_published_parents_batch([child], allowed_projects=_ALL_PROJECTS)
    batch_count = {c.workflow_id: c.referencing_parent_count for c in batch.counts}[child]

    # dup parent (counted once) + cross-project parent; draft and non-sub_workflow excluded
    assert single == batch_count == 2


@pytest.mark.integration
@pytest.mark.asyncio
async def test_batch_single_parity_self_reference(
    test_db_session: AsyncSession, test_user: User, test_project_id: UUID
) -> None:
    """A workflow that references itself is counted once by both the single and batch paths."""
    service = WorkflowService(test_db_session, test_user)
    self_id = uuid4()
    test_db_session.add(
        Workflow(id=self_id, name=f"self-{uuid4().hex[:8]}", created_by=test_user.id, project_id=test_project_id)
    )
    await test_db_session.flush()
    version_id = uuid4()
    test_db_session.add(
        WorkflowVersion(
            id=version_id,
            workflow_id=self_id,
            version=1,
            schema_version="2.0.0",
            workflow_definition=_referencing_def(self_id, 1),
            created_by=test_user.id,
        )
    )
    await test_db_session.flush()
    workflow = await test_db_session.get(Workflow, self_id)
    assert workflow is not None
    workflow.is_enabled = True
    workflow.published_version_id = version_id
    await test_db_session.commit()

    single = await service.count_referencing_published_parents(self_id)
    batch = await service.count_published_parents_batch([self_id], allowed_projects=_ALL_PROJECTS)
    batch_count = {c.workflow_id: c.referencing_parent_count for c in batch.counts}[self_id]
    assert single == batch_count == 1


@pytest.mark.integration
@pytest.mark.asyncio
async def test_published_reference_survives_a_newer_draft_removal(
    test_db_session: AsyncSession, test_user: User, test_project_id: UUID
) -> None:
    """A published parent still counts even after a newer *draft* drops the sub_workflow node.

    The match is against the parent's published version, so an unpublished later draft that removes
    the reference does not change the count. Exercises both the single and batch paths.
    """
    service = WorkflowService(test_db_session, test_user)
    child = await _publish(
        test_db_session,
        created_by=test_user.id,
        project_id=test_project_id,
        definition=_plain_def(),
        name=f"child-{uuid4().hex[:8]}",
    )
    parent_id = await _publish(
        test_db_session,
        created_by=test_user.id,
        project_id=test_project_id,
        definition=_referencing_def(child, 1),
        name=f"parent-{uuid4().hex[:8]}",
    )
    # Add a newer draft (version 2) without the reference; do NOT move published_version_id.
    test_db_session.add(
        WorkflowVersion(
            id=uuid4(),
            workflow_id=parent_id,
            version=2,
            schema_version="2.0.0",
            workflow_definition=_plain_def(),
            created_by=test_user.id,
        )
    )
    await test_db_session.commit()

    single = await service.count_referencing_published_parents(child)
    batch = await service.count_published_parents_batch([child], allowed_projects=_ALL_PROJECTS)
    batch_count = {c.workflow_id: c.referencing_parent_count for c in batch.counts}[child]
    assert single == batch_count == 1


@pytest.mark.integration
@pytest.mark.asyncio
async def test_reference_only_in_a_newer_draft_is_excluded(
    test_db_session: AsyncSession, test_user: User, test_project_id: UUID
) -> None:
    """A reference that exists only in a newer *draft* of an already-published workflow is excluded.

    The published version has no reference, so neither count path includes it until it is published.
    """
    service = WorkflowService(test_db_session, test_user)
    child = await _publish(
        test_db_session,
        created_by=test_user.id,
        project_id=test_project_id,
        definition=_plain_def(),
        name=f"child-{uuid4().hex[:8]}",
    )
    parent_id = await _publish(
        test_db_session,
        created_by=test_user.id,
        project_id=test_project_id,
        definition=_plain_def(),
        name=f"parent-{uuid4().hex[:8]}",
    )
    # Newer draft (version 2) introduces the reference but is not published.
    test_db_session.add(
        WorkflowVersion(
            id=uuid4(),
            workflow_id=parent_id,
            version=2,
            schema_version="2.0.0",
            workflow_definition=_referencing_def(child, 1),
            created_by=test_user.id,
        )
    )
    await test_db_session.commit()

    single = await service.count_referencing_published_parents(child)
    batch = await service.count_published_parents_batch([child], allowed_projects=_ALL_PROJECTS)
    batch_counts = {c.workflow_id: c.referencing_parent_count for c in batch.counts}
    assert single == 0
    assert batch_counts.get(child, 0) == 0


@pytest.mark.integration
@pytest.mark.asyncio
async def test_referencing_parent_count_is_independent_of_page_size_and_cursor(
    test_db_session: AsyncSession, test_user: User, test_project_id: UUID
) -> None:
    """``referencing_parent_count`` reports the full total regardless of limit or cursor."""
    service = WorkflowService(test_db_session, test_user)
    child = uuid4()
    for _ in range(3):
        await _publish(
            test_db_session,
            created_by=test_user.id,
            project_id=test_project_id,
            definition=_referencing_def(child, 1),
            name=f"p-{uuid4().hex[:8]}",
        )

    full = await service.list_published_parents(child, allowed_projects=_ALL_PROJECTS)
    assert full.referencing_parent_count == 3
    assert len(full.resources) == 3

    first = await service.list_published_parents(child, limit=1, allowed_projects=_ALL_PROJECTS)
    assert first.referencing_parent_count == 3  # unchanged by a smaller page
    assert len(first.resources) == 1
    assert first.next is not None

    second = await service.list_published_parents(child, limit=1, cursor=first.next, allowed_projects=_ALL_PROJECTS)
    assert second.referencing_parent_count == 3  # unchanged across the cursor
    assert len(second.resources) == 1
    assert {r.id for r in first.resources}.isdisjoint({r.id for r in second.resources})


@pytest.mark.integration
@pytest.mark.asyncio
async def test_delete_referenced_requires_confirm_and_audits(
    test_db_session: AsyncSession, test_user: User, test_project_id: UUID, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A 409 is not a deletion audit; confirmed deletion records all affected parent ids."""
    from syntara.audit.dispatcher import AuditEventDispatcher
    from syntara.workflows.audit.workflow_lifecycle import WorkflowAction, WorkflowLifecycleEvent
    from syntara.workflows.exceptions import WorkflowReferencedByPublishedParentsError

    actor_id = test_user.id
    service = WorkflowService(test_db_session, test_user)
    child = await _publish(
        test_db_session,
        created_by=actor_id,
        project_id=test_project_id,
        definition=_plain_def(),
        name=f"child-{uuid4().hex[:8]}",
    )
    parent_a = await _publish(
        test_db_session,
        created_by=actor_id,
        project_id=test_project_id,
        definition=_referencing_def(child),
        name=f"parent-a-{uuid4().hex[:8]}",
    )
    parent_b = await _publish(
        test_db_session,
        created_by=actor_id,
        project_id=test_project_id,
        definition=_referencing_def(child),
        name=f"parent-b-{uuid4().hex[:8]}",
    )

    events: list[Any] = []
    monkeypatch.setattr(AuditEventDispatcher, "dispatch", lambda event: events.append(event))

    with pytest.raises(WorkflowReferencedByPublishedParentsError) as exc_info:
        await service.delete_workflow(child)
    assert exc_info.value.referencing_count == 2
    assert exc_info.value.workflow_id == child
    test_db_session.expire_all()
    assert await test_db_session.get(Workflow, child) is not None
    assert events == []

    await service.delete_workflow(child, confirm=True)
    test_db_session.expire_all()
    assert await test_db_session.get(Workflow, child) is None
    deleted = [e for e in events if isinstance(e, WorkflowLifecycleEvent) and e.action == WorkflowAction.DELETED]
    assert len(deleted) == 1
    assert deleted[0].workflow_id == child
    assert deleted[0].actor_id == actor_id
    assert deleted[0].referencing_parent_ids is not None
    assert set(deleted[0].referencing_parent_ids) == {parent_a, parent_b}

    unreferenced = await _publish(
        test_db_session,
        created_by=actor_id,
        project_id=test_project_id,
        definition=_plain_def(),
        name=f"unreferenced-{uuid4().hex[:8]}",
    )
    events.clear()
    await service.delete_workflow(unreferenced)
    unreferenced_deletions = [
        e for e in events if isinstance(e, WorkflowLifecycleEvent) and e.action == WorkflowAction.DELETED
    ]
    assert len(unreferenced_deletions) == 1
    assert unreferenced_deletions[0].workflow_id == unreferenced
    assert unreferenced_deletions[0].actor_id == actor_id
    assert unreferenced_deletions[0].referencing_parent_ids is None


def _ref_node_for(child_id: UUID, trigger_node_id: str, index: int = 0) -> dict[str, Any]:
    return {
        "id": f"sub_{trigger_node_id}_{index}",
        "type": "sub_workflow",
        "parameters": {"workflow_id": str(child_id), "trigger_node_id": trigger_node_id, "input_mapping": {}},
    }


def _def_with_subworkflow_triggers(trigger_ids: list[str]) -> dict[str, Any]:
    return {
        "schema_version": "2.0.0",
        "triggers": [{"id": tid, "type": "subworkflow_trigger", "parameters": {}} for tid in trigger_ids],
        "nodes": [{"id": "s", "type": "script", "parameters": {"language": "bash", "code": "echo hi"}}],
        "edges": [],
    }


@pytest.mark.integration
@pytest.mark.asyncio
async def test_referencing_parent_ids_for_triggers_are_distinct(
    test_db_session: AsyncSession, test_user: User, test_project_id: UUID
) -> None:
    """A parent invoking several of the removed triggers is counted once across the set."""
    service = WorkflowService(test_db_session, test_user)
    child_id = uuid4()
    only_a = await _publish(
        test_db_session,
        created_by=test_user.id,
        project_id=test_project_id,
        definition=_definition([_ref_node_for(child_id, "t1")]),
        name=f"a-{uuid4().hex[:8]}",
    )
    only_b = await _publish(
        test_db_session,
        created_by=test_user.id,
        project_id=test_project_id,
        definition=_definition([_ref_node_for(child_id, "t2")]),
        name=f"b-{uuid4().hex[:8]}",
    )
    both = await _publish(
        test_db_session,
        created_by=test_user.id,
        project_id=test_project_id,
        definition=_definition([_ref_node_for(child_id, "t1"), _ref_node_for(child_id, "t2")]),
        name=f"both-{uuid4().hex[:8]}",
    )

    across = await service.get_referencing_published_parent_ids_for_triggers(child_id, ["t1", "t2"])
    assert sorted(across) == sorted([only_a, only_b, both])
    assert len(across) == len(set(across))  # distinct -- "both" appears once

    just_t1 = await service.get_referencing_published_parent_ids_for_triggers(child_id, ["t1"])
    assert set(just_t1) == {only_a, both}


async def _publish_child_with_trigger(
    session: AsyncSession, *, created_by: UUID, project_id: UUID, trigger_id: str, name: str
) -> tuple[UUID, WorkflowVersion]:
    """Create a published child (v1 has the subworkflow trigger) plus a draft v2 that drops it."""
    workflow_id = uuid4()
    session.add(Workflow(id=workflow_id, name=name, created_by=created_by, project_id=project_id))
    await session.flush()
    v1 = WorkflowVersion(
        id=uuid4(),
        workflow_id=workflow_id,
        version=1,
        schema_version="2.0.0",
        workflow_definition=_def_with_subworkflow_triggers([trigger_id]),
        created_by=created_by,
    )
    v2 = WorkflowVersion(
        id=uuid4(),
        workflow_id=workflow_id,
        version=2,
        schema_version="2.0.0",
        workflow_definition=_def_with_subworkflow_triggers([]),
        created_by=created_by,
    )
    session.add(v1)
    session.add(v2)
    await session.flush()
    workflow = await session.get(Workflow, workflow_id)
    assert workflow is not None
    workflow.is_enabled = True
    workflow.published_version_id = v1.id
    await session.commit()
    return workflow_id, v2


@pytest.mark.integration
@pytest.mark.asyncio
async def test_publish_trigger_removal_gate_requires_confirm_then_audits(
    test_db_session: AsyncSession, test_user: User, test_project_id: UUID
) -> None:
    """Publishing a version that drops a referenced trigger needs confirm; confirmed returns the parents."""
    from syntara.workflows.exceptions import WorkflowPublishTriggerRemovalConfirmationError

    service = WorkflowService(test_db_session, test_user)
    child_id, draft_without_trigger = await _publish_child_with_trigger(
        test_db_session,
        created_by=test_user.id,
        project_id=test_project_id,
        trigger_id="child_trigger",
        name=f"child-{uuid4().hex[:8]}",
    )
    parent = await _publish(
        test_db_session,
        created_by=test_user.id,
        project_id=test_project_id,
        definition=_definition([_ref_node_for(child_id, "child_trigger")]),
        name=f"parent-{uuid4().hex[:8]}",
    )
    child = await test_db_session.get(Workflow, child_id)
    assert child is not None

    with pytest.raises(WorkflowPublishTriggerRemovalConfirmationError) as exc_info:
        await service._check_publish_trigger_removal(child, draft_without_trigger, confirm=False)
    assert exc_info.value.affected_count == 1
    assert exc_info.value.workflow_id == child_id

    affected = await service._check_publish_trigger_removal(child, draft_without_trigger, confirm=True)
    assert affected == [parent]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_publish_trigger_removal_gate_passes_when_no_referenced_trigger_removed(
    test_db_session: AsyncSession, test_user: User, test_project_id: UUID
) -> None:
    """No gate when the removed trigger has no published callers (publishing proceeds normally)."""
    service = WorkflowService(test_db_session, test_user)
    child_id, draft_without_trigger = await _publish_child_with_trigger(
        test_db_session,
        created_by=test_user.id,
        project_id=test_project_id,
        trigger_id="child_trigger",
        name=f"child-{uuid4().hex[:8]}",
    )
    child = await test_db_session.get(Workflow, child_id)
    assert child is not None

    affected = await service._check_publish_trigger_removal(child, draft_without_trigger, confirm=False)
    assert affected == []
