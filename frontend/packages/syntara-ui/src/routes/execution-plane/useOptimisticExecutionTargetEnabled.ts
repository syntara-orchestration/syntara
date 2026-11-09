import type { ExecutionPlaneAPI } from '@syntara/contracts'
import { startTransition, useCallback, useOptimistic } from 'react'

type ExecutionTarget = ExecutionPlaneAPI.components['schemas']['ExecutionTargetRead']

type EnabledUpdate = {
  id: string
  enabled: boolean
}

type PatchExecutionTargetAsync = (args: {
  params: { path: { target_id: string } }
  body: { enabled: boolean }
}) => Promise<unknown>

export type UseOptimisticExecutionTargetEnabledOptions = {
  targets: ExecutionTarget[]
  patchTarget: PatchExecutionTargetAsync
  /** Called after a successful patch (e.g. refetch). Awaited inside the Action so optimistic UI holds until server state converges. */
  onSuccess: () => void | Promise<unknown>
  onError: (title: string, error: unknown) => void
}

function applyEnabledUpdate(targets: ExecutionTarget[], update: EnabledUpdate): ExecutionTarget[] {
  return targets.map((target) => (target.id === update.id ? { ...target, enabled: update.enabled } : target))
}

/**
 * Optimistic enable/disable for execution targets.
 *
 * Flips `enabled` immediately via React 19 `useOptimistic`, then patches the API inside a
 * `startTransition` Action. On failure the Action ends without updating server state, so the
 * switch rolls back automatically.
 *
 * @see https://react.dev/reference/react/useOptimistic
 */
export function useOptimisticExecutionTargetEnabled({
  targets,
  patchTarget,
  onSuccess,
  onError,
}: UseOptimisticExecutionTargetEnabledOptions) {
  const [optimisticTargets, setOptimisticEnabled] = useOptimistic(targets, applyEnabledUpdate)

  const setTargetEnabled = useCallback(
    (target: ExecutionTarget, enabled: boolean) => {
      const { id } = target
      if (!id) return

      startTransition(async () => {
        setOptimisticEnabled({ id, enabled })
        try {
          await patchTarget({
            params: { path: { target_id: id } },
            body: { enabled },
          })
          await onSuccess()
        } catch (error: unknown) {
          onError(enabled ? 'Failed to enable execution target' : 'Failed to disable execution target', error)
        }
      })
    },
    [onError, onSuccess, patchTarget, setOptimisticEnabled]
  )

  return { targets: optimisticTargets, setTargetEnabled }
}
