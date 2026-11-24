import { Content } from '@patternfly/react-core'
import { useCallback, useState } from 'react'

import { SynConfirmationDialog } from '../components/dialogs/SynConfirmationDialog'
import { extractReferencedParentCount, isWorkflowReferencedConfirmationError } from '../utils/apiErrors'

type PendingConfirm = { referencingCount: number; retry: () => void }

/**
 * Shared explicit confirm/retry for the delete "referenced by published parents" 409. A delete
 * entry point calls ``guardDeleteError`` in its mutation error handler: when the error is the
 * referenced-confirmation 409 it opens a confirmation dialog and returns true (so the caller skips
 * its generic error), and on confirm it re-runs the caller-supplied retry (which re-deletes with
 * confirm=true). It never retries on its own, so a referenced workflow is never silently
 * force-deleted, and cancelling the dialog fires no delete at all. Kept separate from the publish
 * trigger-removal confirm so the two 409s stay independently matched.
 */
export function useReferencedDeleteConfirm() {
  const [pending, setPending] = useState<PendingConfirm | null>(null)

  const guardDeleteError = useCallback((error: unknown, retry: () => void): boolean => {
    if (!isWorkflowReferencedConfirmationError(error)) return false
    const referencingCount = extractReferencedParentCount(error)
    // A malformed confirmation (code present, count missing/invalid) is not a usable confirmation:
    // fall through to the generic error path rather than show a misleading dialog or retry.
    if (referencingCount === null) return false
    setPending({ referencingCount, retry })
    return true
  }, [])

  const referencedDeleteConfirmDialog = pending ? (
    <SynConfirmationDialog
      isOpen
      onClose={() => setPending(null)}
      onConfirm={() => {
        const { retry } = pending
        setPending(null)
        retry()
      }}
      title="Delete and break dependent workflows?"
      confirmLabel="Delete anyway"
      confirmVariant="danger"
      titleIconVariant="warning"
    >
      <Content component="p">
        This workflow is used as a sub-workflow by {pending.referencingCount} published workflow(s). Deleting it means
        they will no longer be able to call it. This cannot be undone.
      </Content>
    </SynConfirmationDialog>
  ) : null

  return { guardDeleteError, referencedDeleteConfirmDialog }
}
