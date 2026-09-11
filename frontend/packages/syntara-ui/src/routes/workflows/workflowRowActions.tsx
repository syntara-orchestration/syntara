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

import type { useWorkflowPermissions } from './useWorkflowPermissions'
import type { RowAction } from './WorkflowsTableBody'

type Workflow = WorkflowAPI.components['schemas']['WorkflowRead']

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

export function buildWorkflowRowActions(
  workflow: Workflow,
  permissions: ReturnType<typeof useWorkflowPermissions>,
  isBuiltinProject: boolean,
  callbacks: WorkflowRowActionCallbacks
): RowAction[] {
  if (workflow.is_builtin) return []

  const updatePermissionTooltip = permissions.canUpdate ? undefined : { content: permissions.tooltips.update }
  const duplicatePermissionTooltip = permissions.canCreate ? undefined : { content: permissions.tooltips.duplicate }
  const deletePermissionTooltip = permissions.canDelete ? undefined : { content: permissions.tooltips.delete }
  const noUpdate = isBuiltinProject ? { content: builtinProjectTooltip('edit this workflow') } : updatePermissionTooltip
  const noDuplicate = isBuiltinProject
    ? { content: builtinProjectTooltip('duplicate this workflow') }
    : duplicatePermissionTooltip
  const noRun = permissions.canRun ? undefined : { content: permissions.tooltips.run }
  const noDelete = isBuiltinProject
    ? { content: builtinProjectTooltip('delete this workflow') }
    : deletePermissionTooltip
  const noPublish = isBuiltinProject
    ? { content: builtinProjectTooltip('publish this workflow') }
    : updatePermissionTooltip
  const noUnpublish = isBuiltinProject
    ? { content: builtinProjectTooltip('unpublish this workflow') }
    : updatePermissionTooltip

  return [
    {
      key: 'edit',
      title: <IconLabel icon={<RhUiEditFillIcon />}>Edit workflow</IconLabel>,
      isAriaDisabled: isBuiltinProject || !permissions.canUpdate,
      tooltipProps: noUpdate,
      onClick: () => {
        if (!workflow.id) return
        detachPromise(callbacks.navigate({ to: '/workflow-builder/$workflowId', params: { workflowId: workflow.id } }))
      },
    },
    {
      key: 'run',
      title: <IconLabel icon={<RhUiPlayIcon />}>Run published version</IconLabel>,
      isAriaDisabled: !permissions.canRun || !workflow.published_version_id,
      tooltipProps: !workflow.published_version_id
        ? { content: 'No published version. Go to the workflow editor to run the current version.' }
        : noRun,
      onClick: () => callbacks.onRun(workflow),
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
      isAriaDisabled: isBuiltinProject || !permissions.canCreate,
      tooltipProps: noDuplicate,
      onClick: () => callbacks.onDuplicate(workflow),
    },
    {
      key: 'export',
      title: <IconLabel icon={<RhUiExportIcon />}>Export workflow</IconLabel>,
      onClick: () => callbacks.onExport(workflow),
    },
    {
      key: 'publish',
      title: <IconLabel icon={<RhUiCheckCircleIcon />}>Publish workflow</IconLabel>,
      isAriaDisabled: isBuiltinProject || !permissions.canUpdate,
      tooltipProps: noPublish,
      onClick: () => callbacks.onPublish(workflow),
    },
    ...(workflow.published_version_id == null
      ? []
      : [
          {
            key: 'unpublish',
            title: <IconLabel icon={<RhUiMinusCircleFillIcon />}>Unpublish workflow</IconLabel>,
            isAriaDisabled: isBuiltinProject || !permissions.canUpdate,
            tooltipProps: noUnpublish,
            onClick: () => callbacks.onUnpublish(workflow),
          } satisfies RowAction,
        ]),
    {
      key: 'sep-delete',
      isSeparator: true,
    },
    {
      key: 'delete',
      title: <IconLabel icon={<RhUiTrashIcon />}>Delete workflow</IconLabel>,
      isAriaDisabled: isBuiltinProject || !permissions.canDelete,
      tooltipProps: noDelete,
      isDanger: true,
      onClick: () => callbacks.onDelete(workflow),
    },
  ]
}
