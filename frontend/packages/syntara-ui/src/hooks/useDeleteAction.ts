import { useCallback } from 'react'

import { useAlerts } from '../providers/alerts'
import { getErrorMessage } from '../utils/apiErrors'

type UseDeleteActionOptions<T, P = unknown> = {
  /** Function that performs the delete mutation */
  deleteFn: (
    params: P,
    callbacks: {
      onSuccess: () => void
      onError: (error: unknown) => void
      onSettled: () => void
    }
  ) => void
  /** Build the mutation params from the item */
  buildParams: (item: T) => P
  /** Entity type label for alert messages (e.g., "user", "group", "workflow") */
  entityLabel: string
  /** Get the display name from the item for alert messages */
  getItemName: (item: T) => string
  /** Called after successful deletion (typically refetch the list) */
  onSuccess?: () => void
  /** Called after mutation settles (success or error) — typically close the dialog */
  onSettled?: () => void
  /** Override default success alert title */
  successTitle?: string
  /** Override default error alert title */
  errorTitle?: string
}

/**
 * Encapsulates the repeated delete-with-alerts pattern used across list views.
 *
 * Handles:
 * - Null-checking the item
 * - Calling the mutation with proper callbacks
 * - Showing success/error alerts
 * - Calling onSettled (to close dialog)
 * - Calling onSuccess (to refetch)
 *
 * @example
 * ```tsx
 * const { mutate: deleteUser } = usersClient.useMutation('delete', '/users/{user_id}')
 *
 * const handleDelete = useDeleteAction({
 *   deleteFn: deleteUser,
 *   buildParams: (user) => ({ params: { path: { user_id: user.id } } }),
 *   entityLabel: 'user',
 *   getItemName: (user) => user.username,
 *   onSuccess: () => detachPromise(query.refetch()),
 *   onSettled: () => dispatch({ type: 'CLOSE_DELETE_DIALOG' }),
 * })
 *
 * // In JSX:
 * <SynConfirmationDialog onConfirm={() => handleDelete(userToDelete)} ... />
 * ```
 */
export function useDeleteAction<T, P = unknown>({
  deleteFn,
  buildParams,
  entityLabel,
  getItemName,
  onSuccess,
  onSettled,
  successTitle,
  errorTitle,
}: UseDeleteActionOptions<T, P>): (item: T | null) => void {
  const { showAlert } = useAlerts()

  return useCallback(
    (item: T | null) => {
      if (item === null) return

      const itemName = getItemName(item)
      const params = buildParams(item)

      deleteFn(params, {
        onSuccess: () => {
          showAlert({
            title: successTitle ?? `${entityLabel.charAt(0).toUpperCase() + entityLabel.slice(1)} deleted`,
            description: `${entityLabel.charAt(0).toUpperCase() + entityLabel.slice(1)} "${itemName}" has been deleted successfully.`,
            variant: 'success',
            autoDismiss: true,
          })
          onSuccess?.()
        },
        onError: (error: unknown) => {
          showAlert({
            title: errorTitle ?? 'Delete failed',
            description: `Failed to delete ${entityLabel} "${itemName}": ${getErrorMessage(error)}`,
            variant: 'error',
            autoDismiss: true,
          })
        },
        onSettled: () => {
          onSettled?.()
        },
      })
    },
    [deleteFn, buildParams, entityLabel, getItemName, onSuccess, onSettled, successTitle, errorTitle, showAlert]
  )
}
