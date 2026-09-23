import type { NodeKindsAPI } from '@syntara/contracts'
import { useMemo } from 'react'

import { nodeKindsClient } from '../client'

/** One policy-addressable node attribute declared by a workflow node kind. */
export type NodeKindAttribute = NodeKindsAPI.components['schemas']['NodeAttributeRead']

/** One workflow node kind as the calling principal sees it. */
export type NodeKind = NodeKindsAPI.components['schemas']['NodeKindRead'] & {
  attributes: NodeKindAttribute[]
}

/** Registry grouping that decides which actions may be denied for a kind. */
export type NodeKindCategory = NodeKindsAPI.components['schemas']['NodeKindCategory']

/** Query key of `GET /node_kinds`, for cache invalidation after the kill switch flips. */
export const NODE_KINDS_QUERY_PATH = '/node_kinds' as const

type UseNodeKindsQueryOptions = {
  /** Skip the request (for example while a permission check is still in flight). */
  enabled?: boolean
}

/**
 * Fetch the workflow node-kind registry for the current principal.
 *
 * Every authenticated user may call the endpoint: the response is reference data
 * plus the caller's own `workflow_node:write` verdict per kind (`can_write`) and
 * the platform-wide kill-switch state (`enabled`).
 *
 * @example
 * ```ts
 * const { nodeKinds, nodeKindByKind, isPending } = useNodeKindsQuery()
 * const canAddScript = nodeKindByKind.get('script')?.can_write === true
 * ```
 */
export function useNodeKindsQuery(options?: UseNodeKindsQueryOptions) {
  const query = nodeKindsClient.useQuery('get', NODE_KINDS_QUERY_PATH, {}, { enabled: options?.enabled ?? true })

  const nodeKinds = useMemo<NodeKind[]>(() => query.data?.resources ?? [], [query.data])

  const nodeKindByKind = useMemo(() => new Map(nodeKinds.map((entry) => [entry.kind, entry])), [nodeKinds])

  const disabledKinds = useMemo<ReadonlySet<string>>(
    () => new Set(query.data?.disabled_kinds ?? []),
    [query.data?.disabled_kinds]
  )

  return { query, nodeKinds, nodeKindByKind, disabledKinds }
}

/**
 * Flip the platform-wide kill switch for one node kind (`setting:write`).
 *
 * Unknown kinds return 404; kinds that are not switchable (flow control, including
 * the permission check node) return 422.
 */
export function useSetNodeKindEnabledMutation() {
  return nodeKindsClient.useMutation('put', '/node_kinds/{kind}/enabled')
}
