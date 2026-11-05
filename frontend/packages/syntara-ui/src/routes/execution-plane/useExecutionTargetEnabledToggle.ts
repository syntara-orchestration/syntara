import type { ExecutionPlaneAPI } from '@syntara/contracts'
import { useCallback } from 'react'

import { executionPlaneClient } from '../../client'
import { useDialogState } from '../../hooks/useDialogState'
import { useAlerts } from '../../providers/alerts'
import { getErrorMessage } from '../../utils/apiErrors'

import { useOptimisticExecutionTargetEnabled } from './useOptimisticExecutionTargetEnabled'

type ExecutionTarget = ExecutionPlaneAPI.components['schemas']['ExecutionTargetRead']

export type UseExecutionTargetEnabledToggleOptions = {
  targets: ExecutionTarget[]
  /** Called after a successful enable/disable patch (e.g. refetch). */
  onSuccess: () => void | Promise<unknown>
}

/**
 * Enable/disable wiring for execution targets (list and detail).
 *
 * Disabling opens an informational confirmation dialog first; enabling patches
 * immediately. Optimistic UI + rollback live in {@link useOptimisticExecutionTargetEnabled}.
 */
export function useExecutionTargetEnabledToggle({ targets, onSuccess }: UseExecutionTargetEnabledToggleOptions) {
  const { showAlert } = useAlerts()
  const disableDialog = useDialogState<ExecutionTarget>()

  const { mutateAsync: patchTarget } = executionPlaneClient.useMutation(
    'patch',
    '/api/execution_plane/v1/execution_targets/{target_id}'
  )

  const onError = useCallback(
    (title: string, error: unknown) => {
      showAlert({
        title,
        description: getErrorMessage(error),
        variant: 'danger',
        autoDismiss: true,
      })
    },
    [showAlert]
  )

  const { targets: optimisticTargets, setTargetEnabled } = useOptimisticExecutionTargetEnabled({
    targets,
    patchTarget,
    onSuccess,
    onError,
  })

  const handleToggleEnabled = useCallback(
    (target: ExecutionTarget) => {
      if (!target.id) return
      if (target.enabled) {
        disableDialog.open(target)
        return
      }
      setTargetEnabled(target, true)
    },
    [disableDialog, setTargetEnabled]
  )

  const handleDisable = useCallback(() => {
    const item = disableDialog.item
    disableDialog.close()
    if (!item) return
    setTargetEnabled(item, false)
  }, [disableDialog, setTargetEnabled])

  return {
    targets: optimisticTargets,
    disableDialog,
    handleToggleEnabled,
    handleDisable,
  }
}
