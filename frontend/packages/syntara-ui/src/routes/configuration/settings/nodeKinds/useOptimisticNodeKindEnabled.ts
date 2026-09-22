import { startTransition, useCallback, useOptimistic } from 'react'

import type { NodeKind } from '../../../../hooks/useNodeKindsQuery'

type EnabledUpdate = {
  kind: string
  enabled: boolean
}

type SetNodeKindEnabledAsync = (args: {
  params: { path: { kind: string } }
  body: { enabled: boolean }
}) => Promise<unknown>

export type UseOptimisticNodeKindEnabledOptions = {
  nodeKinds: NodeKind[]
  setEnabled: SetNodeKindEnabledAsync
  /** Awaited inside the Action so the optimistic switch holds until server state converges. */
  onSuccess: (kind: string, enabled: boolean) => void | Promise<unknown>
  onError: (title: string, error: unknown) => void
}

function applyEnabledUpdate(nodeKinds: NodeKind[], update: EnabledUpdate): NodeKind[] {
  return nodeKinds.map((entry) => (entry.kind === update.kind ? { ...entry, enabled: update.enabled } : entry))
}

/**
 * Optimistic kill switch for the node-kind registry table.
 *
 * Flips `enabled` immediately via React 19 `useOptimistic`, then calls
 * `PUT /node_kinds/{kind}/enabled` inside a `startTransition` Action. On failure the
 * Action ends without new server state, so the switch rolls back on its own.
 *
 * @see https://react.dev/reference/react/useOptimistic
 */
export function useOptimisticNodeKindEnabled({
  nodeKinds,
  setEnabled,
  onSuccess,
  onError,
}: UseOptimisticNodeKindEnabledOptions) {
  const [optimisticNodeKinds, setOptimisticEnabled] = useOptimistic(nodeKinds, applyEnabledUpdate)

  const setNodeKindEnabled = useCallback(
    (kind: string, enabled: boolean) => {
      startTransition(async () => {
        setOptimisticEnabled({ kind, enabled })
        try {
          await setEnabled({ params: { path: { kind } }, body: { enabled } })
          await onSuccess(kind, enabled)
        } catch (error: unknown) {
          onError(enabled ? `Failed to enable ${kind} nodes` : `Failed to disable ${kind} nodes`, error)
        }
      })
    },
    [onError, onSuccess, setEnabled, setOptimisticEnabled]
  )

  return { nodeKinds: optimisticNodeKinds, setNodeKindEnabled }
}
