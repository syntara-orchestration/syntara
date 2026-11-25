import { Content } from '@patternfly/react-core'
import { useCallback, useState } from 'react'

import { SynConfirmationDialog } from '../components/dialogs/SynConfirmationDialog'
import { extractPublishTriggerRemovalAffectedCount, isPublishTriggerRemovalConfirmationError } from '../utils/apiErrors'

type PendingConfirm = { affectedCount: number; retry: () => void }

/**
 * Shared explicit confirm/retry for the publish trigger-removal 409. A publish entry point calls
 * ``guardPublishError`` in its mutation error handler: when the error is the trigger-removal
 * confirmation 409 it opens a confirmation dialog and returns true (so the caller skips its generic
 * error), and on confirm it re-runs the caller-supplied retry (which republishes with confirm=true).
 * Never retries on its own, so a publish is never silently forced.
 */
export function useTriggerRemovalPublishConfirm() {
  const [pending, setPending] = useState<PendingConfirm | null>(null)

  const guardPublishError = useCallback((error: unknown, retry: () => void): boolean => {
    if (!isPublishTriggerRemovalConfirmationError(error)) return false
    const affectedCount = extractPublishTriggerRemovalAffectedCount(error)
    // A malformed confirmation (code present, count missing/invalid) is not a usable confirmation:
    // fall through to the generic error path rather than show a misleading dialog or retry.
    if (affectedCount === null) return false
    setPending({ affectedCount, retry })
    return true
  }, [])

  const triggerRemovalConfirmDialog = pending ? (
    <SynConfirmationDialog
      isOpen
      onClose={() => setPending(null)}
      onConfirm={() => {
        const { retry } = pending
        setPending(null)
        retry()
      }}
      title="Publish and break dependent workflows?"
      confirmLabel="Publish anyway"
      confirmVariant="danger"
      titleIconVariant="warning"
    >
      <Content component="p">
        Publishing removes a Subworkflow Trigger used by {pending.affectedCount} published workflow(s). Those workflows
        will stop working. This cannot be undone.
      </Content>
    </SynConfirmationDialog>
  ) : null

  return { guardPublishError, triggerRemovalConfirmDialog }
}
