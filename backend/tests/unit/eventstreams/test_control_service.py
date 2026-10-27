"""Control dispatch, revision conflicts, exceptional grants and global convergence."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.authz.exceptions import AuthorizationDeniedError
from syntara.authz.role_conventions import BUILTIN_POLICIES
from syntara.eventstreams.core.placement import SubscriptionPlacementLease, WorkerIdentity
from syntara.eventstreams.core.runtime import RuntimeState
from syntara.eventstreams.exceptions import EventSubscriptionControlConflictError, EventSubscriptionNotFoundError
from syntara.eventstreams.models.control import EventSubscriptionRecovery, EventSubscriptionRuntime
from syntara.eventstreams.models.controls import (
    SubscriptionControlRequest,
    SubscriptionRecoveryRequest,
    SubscriptionRetireRequest,
)
from syntara.eventstreams.services import control_service as control_module
from syntara.eventstreams.services.control_service import EventSubscriptionControlService
from tests.unit.eventstreams.test_deduplication_store import NOW, binding, delivery
from tests.unit.eventstreams.test_subscription_snapshot import _source, _subscription


@pytest.fixture
def context(monkeypatch):
    subscription = _subscription()
    source = _source(subscription)
    worker = WorkerIdentity(deployment_id=source.deployment_id)
    subscription.assigned_worker_id = worker.worker_id
    subscription.assignment_lease_until = NOW + timedelta(seconds=60)
    lease = SubscriptionPlacementLease(
        subscription_id=subscription.id, owner=worker, confirmed_at=NOW, expires_at=subscription.assignment_lease_until
    )
    placements = AsyncMock(return_value={subscription.id: lease})
    monkeypatch.setattr(control_module, "confirmed_placements", placements)
    workflow = SimpleNamespace(
        id=subscription.workflow_id,
        project_id=subscription.project_id,
        is_enabled=True,
        published_version_id=subscription.published_version_id,
        labels={},
    )
    session = MagicMock(spec=AsyncSession)
    result = MagicMock()
    result.all.return_value = []
    result.first.return_value = None
    session.exec.return_value = result
    user = SimpleNamespace(id=uuid4(), labels={})
    service = EventSubscriptionControlService(session, user, MagicMock())
    monkeypatch.setattr(service, "_load", AsyncMock(return_value=(workflow, subscription, source)))
    return SimpleNamespace(
        subscription=subscription,
        source=source,
        workflow=workflow,
        session=session,
        user=user,
        service=service,
        body=SubscriptionControlRequest(configuration_revision=1, source_generation=1),
        worker=worker,
        placements=placements,
    )


async def test_pause_commits_admission_closure_and_reports_other_workers_pending(context):
    context.session.exec.return_value.all.return_value = [
        EventSubscriptionRuntime(source_id=context.source.id, worker_id="other", configuration_revision=1)
    ]
    response = await context.service.action(context.workflow.id, context.subscription.id, context.body, "pause")
    assert context.subscription.paused
    assert context.subscription.configuration_revision == 2
    assert response.convergence == "pending"
    assert response.applied_revision is None
    context.session.commit.assert_awaited_once()


async def test_stopped_participants_prove_pause_applied(context):
    context.session.exec.return_value.all.return_value = [
        EventSubscriptionRuntime(
            source_id=context.source.id, worker_id="stopped", configuration_revision=1, stopped=True
        )
    ]
    response = await context.service.action(context.workflow.id, context.subscription.id, context.body, "pause")
    assert response.convergence == "applied"
    assert response.applied_revision == 2


async def test_matching_configuration_revision_does_not_prove_new_publication_was_applied(context):
    context.session.exec.return_value.all.return_value = [
        EventSubscriptionRuntime(
            source_id=context.source.id,
            worker_id=str(context.worker.worker_id),
            configuration_revision=1,
            applied_revision=1,
            applied_published_version_id=uuid4(),
        )
    ]
    response = await context.service.response(context.subscription, context.source)
    assert response.convergence == "pending"
    assert response.applied_revision is None


@pytest.mark.parametrize("drained", [False, True])
async def test_convergence_requires_current_owner_and_prior_participant_stop_evidence(context, drained):
    current = EventSubscriptionRuntime(
        source_id=context.source.id,
        worker_id=str(context.worker.worker_id),
        configuration_revision=1,
        applied_revision=1,
        applied_published_version_id=context.subscription.published_version_id,
        runtime_state="active",
    )
    previous = current.model_copy(update={"worker_id": str(uuid4()), "stopped": drained})
    response = await context.service.response(context.subscription, context.source, runtimes=[previous, current])
    assert response.convergence == ("applied" if drained else "pending")
    assert response.runtime_state == RuntimeState.ACTIVE
    assert previous.stopped is drained


async def test_no_confirmed_owner_cannot_reuse_old_applied_or_manufacture_stopped_evidence(context):
    context.placements.return_value = {}
    old = EventSubscriptionRuntime(
        source_id=context.source.id,
        worker_id=str(context.worker.worker_id),
        configuration_revision=1,
        applied_revision=1,
        applied_published_version_id=context.subscription.published_version_id,
        runtime_state="active",
    )
    response = await context.service.response(context.subscription, context.source, runtimes=[old])
    assert response.convergence == "pending"
    assert response.runtime_state is None
    assert not old.stopped


async def test_applied_configuration_does_not_claim_initialization_finished(context):
    current = EventSubscriptionRuntime(
        source_id=context.source.id,
        worker_id=str(context.worker.worker_id),
        configuration_revision=1,
        applied_revision=1,
        applied_published_version_id=context.subscription.published_version_id,
        runtime_state="starting",
    )
    response = await context.service.response(context.subscription, context.source, runtimes=[current])
    assert response.convergence == "applied"
    assert response.runtime_state == RuntimeState.STARTING


@pytest.mark.parametrize("action", ["resume", "retry"])
@pytest.mark.parametrize("invalid", ["unpublished", "retired", "replaced", "disabled"])
async def test_activation_controls_cannot_bypass_publication_or_retirement(context, action, invalid):
    if invalid == "unpublished":
        context.workflow.published_version_id = uuid4()
    elif invalid == "disabled":
        context.workflow.is_enabled = False
    elif invalid == "retired":
        context.subscription.retired = True
    else:
        context.subscription.active_source_generation = 2
    with pytest.raises(EventSubscriptionControlConflictError):
        await context.service.action(context.workflow.id, context.subscription.id, context.body, action)
    context.session.commit.assert_not_awaited()


async def test_retry_preserves_context_and_dispatches_to_existing_recovery_store(context):
    context.subscription.assigned_worker_id = None
    context.subscription.assignment_lease_until = None
    context.placements.return_value = {}
    frozen = context.subscription.model_dump(exclude={"configuration_revision", "updated_by"})
    row = delivery()
    row.frozen_binding = binding()
    identity = row.delivery_identity()
    repository = MagicMock()
    repository.request_scheduling_retry = AsyncMock(return_value=True)
    with (
        patch("syntara.eventstreams.services.control_service.EventConnectionProvider") as provider,
        patch("syntara.eventstreams.services.control_service.EventRetirementService") as retirement,
        patch("syntara.eventstreams.services.control_service.EventDeliveryStore", return_value=repository) as store,
    ):
        provider.return_value.resolve_revision = AsyncMock()
        retirement.return_value.deliveries = AsyncMock(return_value=[row])
        retirement.return_value.assert_no_content_gate = AsyncMock()
        await context.service.action(context.workflow.id, context.subscription.id, context.body, "retry")
    assert context.subscription.model_dump(exclude={"configuration_revision", "updated_by"}) == frozen
    assert context.subscription.configuration_revision == 2
    store.assert_called_once_with(context.session, execution_principal_id=row.frozen_binding.execution_principal_id)
    repository.request_scheduling_retry.assert_awaited_once_with(identity)
    assert row.delivery_identity() == identity


@pytest.mark.parametrize("resolve", [False, True])
async def test_retirement_checks_exceptional_grant_only_for_disposition(context, resolve, monkeypatch):
    grant = AsyncMock()
    monkeypatch.setattr(context.service, "_grant", grant)
    retirement = MagicMock()
    retirement.retire = AsyncMock()
    retirement.can_detach = AsyncMock(return_value=False)
    context.session.exec.return_value.one.return_value = datetime.now(UTC)
    with patch("syntara.eventstreams.services.control_service.EventRetirementService", return_value=retirement):
        await context.service.retire(
            context.workflow.id,
            context.subscription.id,
            SubscriptionRetireRequest(
                configuration_revision=1, source_generation=1, reason="listener_removed", resolve_unscheduled=resolve
            ),
        )
    assert grant.await_args_list == ([(("retire", context.workflow), {})] if resolve else [])
    assert context.source.retirement_authorized_by == context.user.id
    assert context.source.retirement_reason == "listener_removed"


@pytest.mark.parametrize("resolve", [False, True])
async def test_recovery_requires_separate_grants_and_persists_authorized_request(context, resolve, monkeypatch):
    grants = AsyncMock()
    monkeypatch.setattr(context.service, "_grant", grants)
    context.session.get.side_effect = [SimpleNamespace(gap_detected_at=datetime.now(UTC), recovery_revision=0), None]
    with patch("syntara.eventstreams.services.control_service.EventRetirementService") as retirement:
        retirement.return_value.deliveries = AsyncMock(return_value=[])
        retirement.return_value.assert_no_content_gate = AsyncMock()
        response = await context.service.recover(
            context.workflow.id,
            context.subscription.id,
            SubscriptionRecoveryRequest(
                configuration_revision=1,
                source_generation=1,
                partition=2,
                expected_recovery_revision=0,
                policy="current_end",
                reason="offset_expired",
                resolve_unscheduled=resolve,
            ),
        )
    assert [call.args[0] for call in grants.await_args_list] == (["recover", "retire"] if resolve else ["recover"])
    request = context.session.add.call_args.args[0]
    assert isinstance(request, EventSubscriptionRecovery)
    assert request.requested_by == context.user.id
    assert request.resolve_unscheduled is resolve
    assert response.convergence == "pending"
    context.session.commit.assert_awaited_once()


async def test_publish_authority_does_not_imply_exceptional_authority(context):
    context.session.get.return_value = SimpleNamespace(name="project-a")
    with patch(
        "syntara.eventstreams.services.control_service.authorize", return_value=SimpleNamespace(allowed=False)
    ) as authorize:
        with pytest.raises(AuthorizationDeniedError):
            await context.service._grant("recover", context.workflow)
    assert authorize.call_args.args[2].resource_project == "project-a"
    context.session.commit.assert_not_awaited()


@pytest.mark.parametrize("action", ["recover", "retire"])
def test_exceptional_grants_are_admin_only_and_project_scoped(action):
    policies = [
        policy for policy in BUILTIN_POLICIES if policy.resource == "event_subscription" and policy.action == action
    ]
    assert {(policy.scope, policy.roles) for policy in policies} == {
        ("any", ("admin",)),
        ("project", ("project-admin",)),
    }


@pytest.mark.parametrize("missing", ["subscription", "source", "stale"])
async def test_scope_and_revision_are_checked_under_lifecycle_locks(context, missing):
    service = EventSubscriptionControlService(context.session, context.user, MagicMock())
    service.workflows.get_workflow_by_id = AsyncMock(return_value=context.workflow)
    result1, result2, result3 = MagicMock(), MagicMock(), MagicMock()
    result1.one.return_value = context.workflow
    result2.one_or_none.return_value = None if missing == "subscription" else context.subscription
    result3.one_or_none.return_value = None if missing == "source" else context.source
    context.session.exec.side_effect = [result1, result2, result3]
    if missing == "stale":
        context.subscription.configuration_revision = 2
    with pytest.raises(
        EventSubscriptionNotFoundError if missing == "subscription" else EventSubscriptionControlConflictError
    ):
        await service._load(context.workflow.id, context.subscription.id, context.body)
    query = str(context.session.exec.call_args_list[1].args[0])
    assert "workflow_id" in query
    assert "project_id" in query
    assert "FOR UPDATE" in query
    context.session.commit.assert_not_awaited()


@pytest.mark.parametrize("action", ["resume", "retry"])
async def test_controls_preserve_shutdown_carried_permanent_error_gates(context, action):
    with patch("syntara.eventstreams.services.control_service.EventRetirementService") as retirement:
        retirement.return_value.assert_no_content_gate = AsyncMock(
            side_effect=EventSubscriptionControlConflictError("permanent_content_error_requires_activity_log")
        )
        with pytest.raises(EventSubscriptionControlConflictError, match="activity_log"):
            await context.service.action(context.workflow.id, context.subscription.id, context.body, action)
    context.session.commit.assert_not_awaited()


async def test_recovery_can_continue_after_pause_resume_supersedes_an_undispatched_request(context):
    context.service._grant = AsyncMock()
    context.subscription.configuration_revision = 3
    old = EventSubscriptionRecovery(
        source_id=context.source.id,
        partition=0,
        configuration_revision=1,
        expected_recovery_revision=0,
        policy="current_end",
        reason="offset_expired",
        requested_by=context.user.id,
    )
    context.session.get.side_effect = [
        SimpleNamespace(gap_detected_at=datetime.now(UTC), recovery_revision=0, recovery_token=None),
        old,
    ]
    with patch("syntara.eventstreams.services.control_service.EventRetirementService") as retirement:
        retirement.return_value.deliveries = AsyncMock(return_value=[])
        retirement.return_value.assert_no_content_gate = AsyncMock()
        await context.service.recover(
            context.workflow.id,
            context.subscription.id,
            SubscriptionRecoveryRequest(
                configuration_revision=3,
                source_generation=1,
                partition=0,
                expected_recovery_revision=0,
                policy="current_end",
                reason="offset_expired",
            ),
        )
    context.session.delete.assert_awaited_once_with(old)
    assert context.session.add.call_args.args[0].configuration_revision == 3
    context.session.commit.assert_awaited_once()


@pytest.mark.parametrize(("old_ack", "old_resolve"), [(False, False), (True, False), (False, True), (True, True)])
@pytest.mark.parametrize(("ack", "resolve"), [(False, False), (True, False), (False, True), (True, True)])
async def test_pending_recovery_accepts_added_authority_without_a_hold_or_revision_change(
    context, old_ack, old_resolve, ack, resolve
):
    context.service._grant = AsyncMock()
    old = EventSubscriptionRecovery(
        source_id=context.source.id,
        partition=0,
        configuration_revision=1,
        expected_recovery_revision=0,
        policy="current_end",
        reason="offset_expired",
        acknowledge_duplicate_risk=old_ack,
        resolve_unscheduled=old_resolve,
        requested_by=uuid4(),
    )
    context.session.get.side_effect = [
        SimpleNamespace(gap_detected_at=datetime.now(UTC), recovery_revision=0, recovery_token=None),
        old,
    ]
    body = SubscriptionRecoveryRequest(
        configuration_revision=1,
        source_generation=1,
        partition=0,
        expected_recovery_revision=0,
        policy="current_end",
        reason="offset_expired",
        acknowledge_duplicate_risk=ack,
        resolve_unscheduled=resolve,
    )
    with patch("syntara.eventstreams.services.control_service.EventRetirementService") as retirement:
        retirement.return_value.deliveries = AsyncMock(return_value=[])
        retirement.return_value.assert_no_content_gate = AsyncMock()
        if (old_ack and not ack) or (old_resolve and not resolve):
            with pytest.raises(EventSubscriptionControlConflictError, match="recovery_request_pending"):
                await context.service.recover(context.workflow.id, context.subscription.id, body)
            context.session.delete.assert_not_awaited()
            context.session.commit.assert_not_awaited()
            return
        response = await context.service.recover(context.workflow.id, context.subscription.id, body)
    context.session.delete.assert_awaited_once_with(old)
    request = context.session.add.call_args.args[0]
    assert request.configuration_revision == 1
    assert request.expected_recovery_revision == 0
    assert request.acknowledge_duplicate_risk is ack
    assert request.resolve_unscheduled is resolve
    assert request.requested_by == context.user.id
    assert [call.args[0] for call in context.service._grant.await_args_list] == (
        ["recover", "retire"] if resolve else ["recover"]
    )
    assert response.convergence == "pending"
    context.session.commit.assert_awaited_once()


@pytest.mark.parametrize("changed", ["policy", "reason"])
@pytest.mark.parametrize("hold", [None, "held"])
async def test_stronger_recovery_authority_cannot_replace_a_pending_decision(context, changed, hold):
    context.service._grant = AsyncMock()
    old = EventSubscriptionRecovery(
        source_id=context.source.id,
        partition=0,
        configuration_revision=1,
        expected_recovery_revision=0,
        policy="retained_beginning" if changed == "policy" else "current_end",
        reason="operator_recovery" if changed == "reason" else "offset_expired",
        requested_by=context.user.id,
    )
    context.session.get.side_effect = [
        SimpleNamespace(gap_detected_at=datetime.now(UTC), recovery_revision=0, recovery_token=hold),
        old,
    ]
    body = SubscriptionRecoveryRequest(
        configuration_revision=1,
        source_generation=1,
        partition=0,
        expected_recovery_revision=0,
        policy="current_end",
        reason="offset_expired",
        acknowledge_duplicate_risk=True,
        resolve_unscheduled=True,
    )
    with patch("syntara.eventstreams.services.control_service.EventRetirementService") as retirement:
        retirement.return_value.deliveries = AsyncMock(return_value=[])
        retirement.return_value.assert_no_content_gate = AsyncMock()
        with pytest.raises(EventSubscriptionControlConflictError, match="recovery_request_pending"):
            await context.service.recover(context.workflow.id, context.subscription.id, body)
    context.session.delete.assert_not_awaited()
    context.session.commit.assert_not_awaited()


async def test_replacement_cannot_overwrite_a_decision_if_confirmation_already_cleared_the_gap(context):
    context.service._grant = AsyncMock()
    context.session.get.return_value = SimpleNamespace(gap_detected_at=None, recovery_revision=1)
    body = SubscriptionRecoveryRequest(
        configuration_revision=1,
        source_generation=1,
        partition=0,
        expected_recovery_revision=1,
        policy="current_end",
        reason="offset_expired",
        acknowledge_duplicate_risk=True,
    )
    with patch("syntara.eventstreams.services.control_service.EventRetirementService") as retirement:
        retirement.return_value.assert_no_content_gate = AsyncMock()
        with pytest.raises(EventSubscriptionControlConflictError, match="no_recorded_recovery_gap"):
            await context.service.recover(context.workflow.id, context.subscription.id, body)
    context.session.delete.assert_not_awaited()
    context.session.add.assert_not_called()
    context.session.commit.assert_not_awaited()


async def test_retry_does_not_acknowledge_a_wakeup_that_an_active_claim_could_lose(context):
    row = delivery()
    row.frozen_binding = binding()
    repository = MagicMock()
    repository.request_scheduling_retry = AsyncMock(return_value=False)
    with (
        patch("syntara.eventstreams.services.control_service.EventConnectionProvider") as provider,
        patch("syntara.eventstreams.services.control_service.EventRetirementService") as retirement,
        patch("syntara.eventstreams.services.control_service.EventDeliveryStore", return_value=repository),
    ):
        provider.return_value.resolve_revision = AsyncMock()
        retirement.return_value.assert_no_content_gate = AsyncMock()
        retirement.return_value.deliveries = AsyncMock(return_value=[row])
        with pytest.raises(EventSubscriptionControlConflictError, match="retry_busy"):
            await context.service.action(context.workflow.id, context.subscription.id, context.body, "retry")
    context.session.commit.assert_not_awaited()
    assert context.subscription.configuration_revision == 1
