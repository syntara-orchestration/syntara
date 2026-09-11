import { reportDetachedRejection } from '../../utils/detachPromise'

type AsyncResult = () => Promise<unknown>

function assertAssignmentId(data: unknown): string {
  if (
    data !== null &&
    typeof data === 'object' &&
    'id' in data &&
    typeof data.id === 'string' &&
    (data as { id: string }).id.length > 0
  ) {
    return (data as { id: string }).id
  }
  throw new Error(
    'Role assignment succeeded but the response did not include an assignment id. Your previous assignment was not removed; refresh the page or contact an administrator.'
  )
}

/**
 * Creates the new role assignment first, then removes the previous one.
 *
 * This avoids a privilege gap where the principal temporarily had no assignment
 * (delete-then-create). Trade-off: until `deleteOld` completes, the principal may
 * hold both roles at once (including a short window where a higher-privilege new
 * role is active alongside the old one). An atomic server-side swap would avoid
 * that overlap; this client flow matches the available APIs.
 *
 * If removing the old assignment fails after the new one was created, the new
 * assignment is revoked so effective permissions match the prior state when possible.
 * If both delete and revoke fail, the error is reported via `globalThis.reportError`
 * when available (for monitoring) and still thrown so the UI can surface recovery
 * details (`newAssignmentId` on `error.cause`).
 */
export async function assignNewThenDeleteOldWithRollback(options: {
  assignNew: AsyncResult
  deleteOld: AsyncResult
  revokeNew: (newAssignmentId: string) => Promise<unknown>
}): Promise<void> {
  const { assignNew, deleteOld, revokeNew } = options
  const assignResult = await assignNew()
  const newAssignmentId = assertAssignmentId(assignResult)

  try {
    await deleteOld()
  } catch (deleteError) {
    try {
      await revokeNew(newAssignmentId)
    } catch (revokeError) {
      const deleteMsg = deleteError instanceof Error ? deleteError.message : String(deleteError)
      const revokeMsg = revokeError instanceof Error ? revokeError.message : String(revokeError)
      const combinedError = new Error(
        `Could not complete role change: removing the previous assignment failed and revoking the new assignment also failed. ` +
          `Manual recovery may be required. New assignment id: ${newAssignmentId}. ` +
          `Delete error: ${deleteMsg}. Revoke error: ${revokeMsg}.`
      )
      ;(combinedError as Error & { cause?: unknown }).cause = {
        deleteError,
        revokeError,
        newAssignmentId,
      }
      reportDetachedRejection(combinedError)
      throw combinedError
    }
    throw deleteError instanceof Error ? deleteError : new Error(String(deleteError))
  }
}
