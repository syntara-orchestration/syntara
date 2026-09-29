import { useQuery } from '@tanstack/react-query'

import { accessFetchClient } from '../routes/access/accessClient'

type UseCanIResult = {
  /** Whether the current user has the requested permission. `false` until the check resolves. */
  allowed: boolean
  /** `true` while the API call is in flight. */
  isChecking: boolean
  /** `true` when the permission check failed (network/server error). */
  isError: boolean
}

type UseCanIOptions = {
  /** Scope the check to a specific resource instance (e.g. `project:my-project`). */
  resourceId?: string
  /** Concrete project name or UUID for project-scoped policy matching. */
  resourceProject?: string
  /** Labels on the resource being checked (for example, a workflow node kind). */
  resourceLabels?: Record<string, string>
  /**
   * When true, allow if the user has the permission in any project
   * (`check_any_project` on `POST /authz/can_i`). Prefer a concrete
   * `resourceProject` when the page already has project context.
   */
  checkAnyProject?: boolean
  /** Skip the API call when `false`. Defaults to `true`. */
  enabled?: boolean
}

/**
 * Checks a single permission via `POST /authz/can_i`.
 *
 * Safe-false default: returns `{ allowed: false }` until the check completes
 * or if the request fails, so gated UI stays hidden/disabled until confirmed.
 *
 * Uses TanStack Query for caching and deduplication — two components calling
 * `useCanI('read', 'setting')` share a single API request. Invalidate all
 * permission caches after role changes with `invalidateAuthzCaches(queryClient)`.
 *
 * @example
 * ```ts
 * const { allowed: canDelete } = useCanI('delete', 'workflow')
 * const { allowed: canAssign } = useCanI('assign', 'role-assignment', { checkAnyProject: true })
 * const { allowed: canUpdate } = useCanI('update', 'workflow', { resourceProject: projectId })
 * ```
 */
export function useCanI(action: string, resourceType: string, options?: UseCanIOptions): UseCanIResult {
  // Prefer concrete project scope; never send both (API rejects the mix).
  const checkAnyProject = Boolean(options?.checkAnyProject && !options?.resourceProject)
  const body = {
    action,
    resource_type: resourceType,
    ...(options?.resourceId ? { resource_id: options.resourceId } : {}),
    ...(options?.resourceLabels ? { resource_labels: options.resourceLabels } : {}),
    ...(options?.resourceProject ? { resource_project: options.resourceProject } : {}),
    ...(checkAnyProject ? { check_any_project: true } : {}),
  }

  const { data, isLoading, isError } = useQuery({
    queryKey: ['authz', 'can_i', body],
    queryFn: () =>
      accessFetchClient.POST('/authz/can_i', {
        body,
      }),
    enabled: options?.enabled !== false,
    select: (res) => res.data?.allowed === true,
    staleTime: Infinity,
    retry: false,
  })

  return { allowed: data ?? false, isChecking: isLoading, isError }
}
