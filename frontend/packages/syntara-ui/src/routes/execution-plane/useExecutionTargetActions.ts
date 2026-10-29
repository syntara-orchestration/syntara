import type { ExecutionPlaneAPI } from '@syntara/contracts'
import { useCallback } from 'react'

import { executionPlaneClient } from '../../client'
import { useDeleteAction } from '../../hooks/useDeleteAction'
import { useDialogState } from '../../hooks/useDialogState'

type ExecutionTarget = ExecutionPlaneAPI.components['schemas']['ExecutionTargetFacadeRead']

type DeleteParams = {
  params: { path: { target_id: string } }
}

type UseExecutionTargetActionsOptions = {
  /** Called after a successful 202 (e.g. refetch the list or navigate away). */
  onSuccess?: () => void
}

/**
 * Dialog + delete mutation wiring for execution targets (list and detail).
 *
 * DELETE returns 202 Accepted; treat that as success. The target may remain
 * listed briefly while draining completes independently.
 */
export function useExecutionTargetActions({ onSuccess }: UseExecutionTargetActionsOptions = {}) {
  const deleteDialog = useDialogState<ExecutionTarget>()

  const { mutate: deleteTarget } = executionPlaneClient.useMutation(
    'delete',
    '/api/execution_plane/v1/execution_targets/{target_id}'
  )

  const buildParams = useCallback(
    (target: ExecutionTarget): DeleteParams => ({
      params: { path: { target_id: target.id } },
    }),
    []
  )

  const getItemName = useCallback((target: ExecutionTarget) => target.name, [])

  const confirmDelete = useDeleteAction<ExecutionTarget, DeleteParams>({
    deleteFn: deleteTarget,
    buildParams,
    entityLabel: 'execution target',
    getItemName,
    successTitle: 'Deletion accepted',
    onSuccess,
    onSettled: () => deleteDialog.close(),
  })

  const handleDelete = useCallback(() => {
    confirmDelete(deleteDialog.item)
  }, [confirmDelete, deleteDialog.item])

  return {
    deleteDialog,
    handleDelete,
  }
}
