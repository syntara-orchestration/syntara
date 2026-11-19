import {
  RhUiCheckCircleIcon,
  RhUiDuplicateIcon,
  RhUiEditFillIcon,
  RhUiExportIcon,
  RhUiHistoryIcon,
  RhUiMinusCircleFillIcon,
  RhUiPlayIcon,
  RhUiTrashIcon,
} from '@patternfly/react-icons'
import type { WorkflowAPI } from '@syntara/contracts'
import { useNavigate } from '@tanstack/react-router'

import { IconLabel } from '../../components/IconLabel'
import { builtinProjectTooltip } from '../../hooks/permissionUtils'
import { detachPromise } from '../../utils/detachPromise'

import { getStepTypePermissionMessage } from './useStepTypePermissions'
import type { StepTypePermissions } from './useStepTypePermissions'
import type { useWorkflowPermissions } from './useWorkflowPermissions'
import type { RowAction } from './WorkflowsTableBody'

type Workflow = WorkflowAPI.components['schemas']['WorkflowRead']
type WorkflowPermissions = ReturnType<typeof useWorkflowPermissions>
type ActionTooltip = { content: string } | undefined

export type WorkflowRowActionCallbacks = {
  navigate: ReturnType<typeof useNavigate>
  onRun: (wf: Workflow) => void
  onDuplicate: (wf: Workflow) => void
  onExport: (wf: Workflow) => void
  onPublish: (wf: Workflow) => void
  onUnpublish: (wf: Workflow) => void
  onDelete: (wf: Workflow) => void
  isDuplicating: boolean
}

export type BuildWorkflowRowActionsParams = {
  workflow: Workflow
  permissions: WorkflowPermissions
  isBuiltinProject: boolean
  callbacks: WorkflowRowActionCallbacks
  stepTypePermissions?: StepTypePermissions
}

function actionIfAllowed(isAllowed: boolean, action: () => void): (() => void) | undefined {
  return isAllowed ? action : undefined
}

function runActionTooltip(hasPublishedVersion: boolean, canRun: boolean, runPermissionTooltip: string): ActionTooltip {
  if (!hasPublishedVersion) {
    return { content: 'No published version. Go to the workflow editor to run the current version.' }
  }
  return canRun ? undefined : { content: runPermissionTooltip }
}

export function buildWorkflowRowActions({
  workflow,
  permissions,
  isBuiltinProject,
  callbacks,
  stepTypePermissions,
}: BuildWorkflowRowActionsParams): RowAction[] {
  if (workflow.is_builtin) return []
  const canAuthor = stepTypePermissions?.canAuthor ?? true
  const stepTypeTooltip =
    stepTypePermissions && !canAuthor ? { content: getStepTypePermissionMessage(stepTypePermissions) } : undefined
  /** Builtin beats RBAC beats step-type denial, mirroring the disabled flags. */
  const tooltip = (action: string, allowed: boolean, permissionMessage: string): ActionTooltip => {
    if (isBuiltinProject) return { content: builtinProjectTooltip(action) }
    if (!allowed) return { content: permissionMessage }
    return stepTypeTooltip
  }

  const gated = (rbacAllowed: boolean) => isBuiltinProject || !rbacAllowed || !canAuthor
  const updateDisabled = gated(permissions.canUpdate)
  const duplicateDisabled = gated(permissions.canCreate)
  const deleteDisabled = gated(permissions.canDelete)
  const hasPublishedVersion = workflow.published_version_id != null
  const runDisabled = !permissions.canRun || !hasPublishedVersion

  const actions: RowAction[] = []
  if (stepTypePermissions?.isError) {
    actions.push({
      key: 'retry-step-type-permissions',
      title: 'Retry step-type permission check',
      onClick: () => detachPromise(stepTypePermissions.retry()),
    })
  }
  actions.push(
    {
      key: 'edit',
      title: <IconLabel icon={<RhUiEditFillIcon />}>Edit workflow</IconLabel>,
      isAriaDisabled: updateDisabled,
      tooltipProps: tooltip('edit this workflow', permissions.canUpdate, permissions.tooltips.update),
      onClick: actionIfAllowed(!updateDisabled, () => {
        detachPromise(callbacks.navigate({ to: '/workflow-builder/$workflowId', params: { workflowId: workflow.id } }))
      }),
    },
    {
      key: 'run',
      title: <IconLabel icon={<RhUiPlayIcon />}>Run published version</IconLabel>,
      isAriaDisabled: runDisabled,
      tooltipProps: runActionTooltip(hasPublishedVersion, permissions.canRun, permissions.tooltips.run),
      onClick: actionIfAllowed(!runDisabled, () => callbacks.onRun(workflow)),
    },
    {
      key: 'history',
      title: <IconLabel icon={<RhUiHistoryIcon />}>View run history</IconLabel>,
      onClick: () => {
        detachPromise(callbacks.navigate({ to: '/executions', search: { workflow_id: workflow.id } }))
      },
    },
    {
      key: 'duplicate',
      title: <IconLabel icon={<RhUiDuplicateIcon />}>Duplicate workflow</IconLabel>,
      isDisabled: callbacks.isDuplicating,
      isAriaDisabled: duplicateDisabled,
      tooltipProps: tooltip('duplicate this workflow', permissions.canCreate, permissions.tooltips.duplicate),
      onClick: actionIfAllowed(!duplicateDisabled, () => callbacks.onDuplicate(workflow)),
    },
    {
      key: 'export',
      title: <IconLabel icon={<RhUiExportIcon />}>Export workflow</IconLabel>,
      onClick: () => callbacks.onExport(workflow),
    },
    {
      key: 'publish',
      title: <IconLabel icon={<RhUiCheckCircleIcon />}>Publish workflow</IconLabel>,
      isAriaDisabled: updateDisabled,
      tooltipProps: tooltip('publish this workflow', permissions.canUpdate, permissions.tooltips.update),
      onClick: actionIfAllowed(!updateDisabled, () => callbacks.onPublish(workflow)),
    }
  )
  if (hasPublishedVersion) {
    actions.push({
      key: 'unpublish',
      title: <IconLabel icon={<RhUiMinusCircleFillIcon />}>Unpublish workflow</IconLabel>,
      isAriaDisabled: updateDisabled,
      tooltipProps: tooltip('unpublish this workflow', permissions.canUpdate, permissions.tooltips.update),
      onClick: actionIfAllowed(!updateDisabled, () => callbacks.onUnpublish(workflow)),
    })
  }
  actions.push(
    { key: 'sep-delete', isSeparator: true },
    {
      key: 'delete',
      title: <IconLabel icon={<RhUiTrashIcon />}>Delete workflow</IconLabel>,
      isAriaDisabled: deleteDisabled,
      tooltipProps: tooltip('delete this workflow', permissions.canDelete, permissions.tooltips.delete),
      isDanger: true,
      onClick: actionIfAllowed(!deleteDisabled, () => callbacks.onDelete(workflow)),
    }
  )
  return actions
}
