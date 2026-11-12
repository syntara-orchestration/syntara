import type { NodeKindsAPI } from '@syntara/contracts'
import { useMemo } from 'react'

import { nodeKindsClient } from '../client'

/** One workflow step type as the calling principal sees it in one project. */
export type NodeKind = NodeKindsAPI.components['schemas']['StepTypePermissionRead']

/** Why the caller may not author one step type. */
export type BlockedStepType = NodeKindsAPI.components['schemas']['StepTypeBlockedBy']

/** Path of `GET /node_kinds`, for cache invalidation after policy or role changes. */
export const NODE_KINDS_QUERY_PATH = '/node_kinds' as const

type UseNodeKindsQueryOptions = {
  /** Skip the request (for example while no project is selected yet). */
  enabled?: boolean
}

/**
 * Fetch the step-type permissions for the current principal in one project.
 *
 * Every authenticated user may call the endpoint: the response is reference
 * data plus the caller's own `step_type:write` verdict per kind (`can_write`)
 * and, when blocked, the policy that blocks it (`blocked_by`). One request
 * covers every step type, so the add-step panel never needs per-kind `can_i`
 * calls.
 *
 * The query is keyed by project: switching projects refetches, because a
 * project deny only applies in that project.
 *
 * @example
 * ```ts
 * const { nodeKindByKind, isUnavailable } = useNodeKindsQuery(projectId)
 * const script = nodeKindByKind.get('script')
 * const canAddScript = script?.can_write === true
 * ```
 */
export function useNodeKindsQuery(projectId: string | null | undefined, options?: UseNodeKindsQueryOptions) {
  const enabled = (options?.enabled ?? true) && Boolean(projectId)

  const query = nodeKindsClient.useQuery(
    'get',
    NODE_KINDS_QUERY_PATH,
    { params: { query: { project_id: projectId ?? '' } } },
    { enabled }
  )

  const nodeKinds = useMemo<NodeKind[]>(() => query.data ?? [], [query.data])

  const nodeKindByKind = useMemo(() => new Map(nodeKinds.map((entry) => [entry.kind, entry])), [nodeKinds])

  // Fail closed: when the endpoint fails or returns nothing, the panel must
  // not claim everything is allowed. The server still rejects the save.
  const isUnavailable = enabled && (!query.isSuccess || nodeKinds.length === 0)

  return { query, nodeKinds, nodeKindByKind, isUnavailable }
}
