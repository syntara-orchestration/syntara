import type { ExecutionPlaneAPI } from '@syntara/contracts'
import { useCallback, useRef, useState } from 'react'

import { executionPlaneClient } from '../../client'
import { useAlerts } from '../../providers/alerts'
import { getErrorMessage } from '../../utils/apiErrors'

type ExecutionTarget = ExecutionPlaneAPI.components['schemas']['ExecutionTargetRead']
type ExecutionTargetHealthResult = ExecutionPlaneAPI.components['schemas']['ExecutionTargetHealthResult']

/**
 * On-demand execution-target connection probe (list + detail kebabs).
 *
 * Calls GET .../execution_targets/{id}/health. Guards duplicate clicks per
 * target while that target's probe is in flight; other targets may probe
 * concurrently.
 */
export function useExecutionTargetTestConnection() {
  const { showAlert } = useAlerts()
  // Per-target Set (not mutation.isPending): supports concurrent row probes and blocks
  // same-id double-clicks before React re-renders. Ref is the sync source of truth.
  const testingTargetIdsRef = useRef(new Set<string>())
  const [testingTargetIds, setTestingTargetIds] = useState<ReadonlySet<string>>(() => new Set())

  const { mutate: probeHealth } = executionPlaneClient.useMutation(
    'get',
    '/api/execution_plane/v1/execution_targets/{target_id}/health'
  )

  const isTestingTarget = useCallback((targetId: string) => testingTargetIds.has(targetId), [testingTargetIds])

  const testConnection = useCallback(
    (target: ExecutionTarget) => {
      if (testingTargetIdsRef.current.has(target.id)) {
        return
      }

      testingTargetIdsRef.current.add(target.id)
      setTestingTargetIds(new Set(testingTargetIdsRef.current))

      probeHealth(
        { params: { path: { target_id: target.id } } },
        {
          onSuccess: (result: ExecutionTargetHealthResult) => {
            if (result.healthy && !result.skipped) {
              showAlert({
                title: 'Connection successful',
                description: `Successfully connected to execution target "${target.name}".`,
                variant: 'success',
                autoDismiss: true,
              })
              return
            }

            showAlert({
              title: 'Connection failed',
              description: result.message?.trim() || `Could not connect to execution target "${target.name}".`,
              variant: 'danger',
              autoDismiss: true,
            })
          },
          onError: (error: unknown) => {
            showAlert({
              title: 'Connection failed',
              description: getErrorMessage(error),
              variant: 'danger',
              autoDismiss: true,
            })
          },
          onSettled: () => {
            testingTargetIdsRef.current.delete(target.id)
            setTestingTargetIds(new Set(testingTargetIdsRef.current))
          },
        }
      )
    },
    [probeHealth, showAlert]
  )

  return {
    testConnection,
    isTestingTarget,
  }
}
