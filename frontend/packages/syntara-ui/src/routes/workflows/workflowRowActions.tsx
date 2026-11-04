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

type WorkflowActionContext = BuildWorkflowRowActionsParams & {
  canAuthor: boolean
  noUpdate: ActionTooltip
  noDuplicate: ActionTooltip
  noRun: ActionTooltip
  noPublish: ActionTooltip
  noUnpublish: ActionTooltip
  noDelete: ActionTooltip
}

function getActionTooltip(options: {
  isBuiltinProject: boolean
  action: string
  permissionAllowed: boolean
  permissionMessage: string
  stepTypeTooltip?: ActionTooltip
}): ActionTooltip {
  if (options.isBuiltinProject) return { content: builtinProjectTooltip(options.action) }
  if (!options.permissionAllowed) return { content: options.permissionMessage }
  return options.stepTypeTooltip
}

function actionIfAllowed(isAllowed: boolean, action: () => void): (() => void) | undefined {
  return isAllowed ? action : undefined
}

function buildEditAction(context: WorkflowActionContext): RowAction {
  const { callbacks, isBuiltinProject, permissions, workflow, canAuthor, noUpdate } = context
  return {
    key: 'edit',
    title: <IconLabel icon={<RhUiEditFillIcon />}>Edit workflow</IconLabel>,
    isAriaDisabled: isBuiltinProject || !permissions.canUpdate || !canAuthor,
    tooltipProps: noUpdate,
    onClick: actionIfAllowed(!isBuiltinProject && permissions.canUpdate && canAuthor, () => {
      detachPromise(callbacks.navigate({ to: '/workflow-builder/$workflowId', params: { workflowId: workflow.id } }))
    }),
  }
}

function buildRunAction(context: WorkflowActionContext): RowAction {
  const { callbacks, permissions, workflow, noRun } = context
  const hasPublishedVersion = workflow.published_version_id != null
  return {
    key: 'run',
    title: <IconLabel icon={<RhUiPlayIcon />}>Run published version</IconLabel>,
    isAriaDisabled: !permissions.canRun || !hasPublishedVersion,
    tooltipProps: hasPublishedVersion
      ? noRun
      : { content: 'No published version. Go to the workflow editor to run the current version.' },
    onClick: actionIfAllowed(permissions.canRun && hasPublishedVersion, () => callbacks.onRun(workflow)),
  }
}

function buildHistoryAction(context: WorkflowActionContext): RowAction {
  const { callbacks, workflow } = context
  return {
    key: 'history',
    title: <IconLabel icon={<RhUiHistoryIcon />}>View run history</IconLabel>,
    onClick: () => {
      detachPromise(callbacks.navigate({ to: '/executions', search: { workflow_id: workflow.id } }))
    },
  }
}

function buildDuplicateAction(context: WorkflowActionContext): RowAction {
  const { callbacks, isBuiltinProject, permissions, workflow, canAuthor, noDuplicate } = context
  return {
    key: 'duplicate',
    title: <IconLabel icon={<RhUiDuplicateIcon />}>Duplicate workflow</IconLabel>,
    isDisabled: callbacks.isDuplicating,
    isAriaDisabled: isBuiltinProject || !permissions.canCreate || !canAuthor,
    tooltipProps: noDuplicate,
    onClick: actionIfAllowed(!isBuiltinProject && permissions.canCreate && canAuthor, () =>
      callbacks.onDuplicate(workflow)
    ),
  }
}

function buildExportAction(context: WorkflowActionContext): RowAction {
  const { callbacks, workflow } = context
  return {
    key: 'export',
    title: <IconLabel icon={<RhUiExportIcon />}>Export workflow</IconLabel>,
    onClick: () => callbacks.onExport(workflow),
  }
}

function buildPublishAction(context: WorkflowActionContext): RowAction {
  const { callbacks, isBuiltinProject, permissions, workflow, canAuthor, noPublish } = context
  return {
    key: 'publish',
    title: <IconLabel icon={<RhUiCheckCircleIcon />}>Publish workflow</IconLabel>,
    isAriaDisabled: isBuiltinProject || !permissions.canUpdate || !canAuthor,
    tooltipProps: noPublish,
    onClick: actionIfAllowed(!isBuiltinProject && permissions.canUpdate && canAuthor, () =>
      callbacks.onPublish(workflow)
    ),
  }
}

function buildUnpublishAction(context: WorkflowActionContext): RowAction {
  const { callbacks, isBuiltinProject, permissions, workflow, canAuthor, noUnpublish } = context
  return {
    key: 'unpublish',
    title: <IconLabel icon={<RhUiMinusCircleFillIcon />}>Unpublish workflow</IconLabel>,
    isAriaDisabled: isBuiltinProject || !permissions.canUpdate || !canAuthor,
    tooltipProps: noUnpublish,
    onClick: actionIfAllowed(!isBuiltinProject && permissions.canUpdate && canAuthor, () =>
      callbacks.onUnpublish(workflow)
    ),
  }
}

function buildDeleteAction(context: WorkflowActionContext): RowAction {
  const { callbacks, isBuiltinProject, permissions, workflow, canAuthor, noDelete } = context
  return {
    key: 'delete',
    title: <IconLabel icon={<RhUiTrashIcon />}>Delete workflow</IconLabel>,
    isAriaDisabled: isBuiltinProject || !permissions.canDelete || !canAuthor,
    tooltipProps: noDelete,
    isDanger: true,
    onClick: actionIfAllowed(!isBuiltinProject && permissions.canDelete && canAuthor, () =>
      callbacks.onDelete(workflow)
    ),
  }
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
  const context: WorkflowActionContext = {
    workflow,
    permissions,
    isBuiltinProject,
    callbacks,
    stepTypePermissions,
    canAuthor,
    noUpdate: getActionTooltip({
      isBuiltinProject,
      action: 'edit this workflow',
      permissionAllowed: permissions.canUpdate,
      permissionMessage: permissions.tooltips.update,
      stepTypeTooltip,
    }),
    noDuplicate: getActionTooltip({
      isBuiltinProject,
      action: 'duplicate this workflow',
      permissionAllowed: permissions.canCreate,
      permissionMessage: permissions.tooltips.duplicate,
      stepTypeTooltip,
    }),
    noRun: permissions.canRun ? undefined : { content: permissions.tooltips.run },
    noPublish: getActionTooltip({
      isBuiltinProject,
      action: 'publish this workflow',
      permissionAllowed: permissions.canUpdate,
      permissionMessage: permissions.tooltips.update,
      stepTypeTooltip,
    }),
    noUnpublish: getActionTooltip({
      isBuiltinProject,
      action: 'unpublish this workflow',
      permissionAllowed: permissions.canUpdate,
      permissionMessage: permissions.tooltips.update,
      stepTypeTooltip,
    }),
    noDelete: getActionTooltip({
      isBuiltinProject,
      action: 'delete this workflow',
      permissionAllowed: permissions.canDelete,
      permissionMessage: permissions.tooltips.delete,
      stepTypeTooltip,
    }),
  }
  const actions: RowAction[] = []
  if (stepTypePermissions?.isError) {
    actions.push({
      key: 'retry-step-type-permissions',
      title: 'Retry step-type permission check',
      onClick: () => detachPromise(stepTypePermissions.retry()),
    })
  }
  actions.push(
    buildEditAction(context),
    buildRunAction(context),
    buildHistoryAction(context),
    buildDuplicateAction(context),
    buildExportAction(context),
    buildPublishAction(context)
  )
  if (workflow.published_version_id != null) actions.push(buildUnpublishAction(context))
  actions.push({ key: 'sep-delete', isSeparator: true }, buildDeleteAction(context))
  return actions
}
