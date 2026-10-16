import { useWhoCanProjectUsers } from './useWhoCanProjectUsers'

/**
 * Hook to fetch all users who have form_prompt:submit permission in a project.
 *
 * Uses /authz/who_can endpoint with cursor pagination to fetch all authorized users.
 * The query is disabled until a projectId is provided — the form prompt node form shows a
 * "select a project" prompt in the meantime rather than firing an unscoped request.
 *
 * If the endpoint returns 403, the hook surfaces `isPermissionDenied: true` so the
 * UI can offer a manual-input fallback instead of an empty dropdown.
 *
 * @param projectId - Project ID to scope the permission check. The query does not
 *                    run until this is a non-empty string.
 * @returns Object containing users array, loading state, permission-denied flag, and error
 */
export function useFormPromptSubmitUsers(projectId?: string | null) {
  return useWhoCanProjectUsers({
    projectId,
    action: 'submit',
    resourceType: 'form_prompt',
    queryKeyPrefix: 'form-prompt-submit-users',
  })
}
