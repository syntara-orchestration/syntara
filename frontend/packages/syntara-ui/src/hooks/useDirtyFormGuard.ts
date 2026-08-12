import { useCallback, useEffect, useRef } from 'react'

import { useUnsavedChanges } from '../app/useUnsavedChanges'

type DirtyFormGuardOptions = {
  /** Whether the form currently has unsaved changes. */
  isDirty: boolean
  /** Save the form and return true on success, false on failure. Omit to hide the "Save" button in the modal. */
  onSave?: () => Promise<boolean>
  /** Reset the form to its clean state when the user discards changes. */
  onDiscard?: () => void
  /** Modal title, e.g. "Save settings?" */
  title: string
  /** Modal body text, e.g. "You have unsaved changes." */
  body: string
  /** Label for the save button in the modal. Defaults to "Save". */
  saveLabel?: string
  /**
   * Whether this guard is active. Defaults to true. Set to false when the guarded
   * surface is mounted but not visible (e.g. an inactive tab in a tabbed detail view).
   */
  isActive?: boolean
}

/**
 * Registers an unsaved-changes guard with the {@link UnsavedChangesProvider}.
 * When the user navigates away while `isDirty` is true, a confirmation modal
 * prompts them to save, discard, or cancel.
 *
 * Handles ref tracking and effect cleanup internally — callers just pass
 * reactive values and stable callbacks.
 */
export function useDirtyFormGuard({
  isDirty,
  onSave,
  onDiscard,
  title,
  body,
  saveLabel,
  isActive = true,
}: DirtyFormGuardOptions): { dismiss: () => void } {
  const { registerDirtyCheck } = useUnsavedChanges()

  const unregisterRef = useRef<(() => void) | null>(null)

  const isDirtyRef = useRef(isDirty)
  useEffect(() => {
    isDirtyRef.current = isDirty
  })

  const onSaveRef = useRef(onSave)
  useEffect(() => {
    onSaveRef.current = onSave
  })

  const onDiscardRef = useRef(onDiscard)
  useEffect(() => {
    onDiscardRef.current = onDiscard
  })

  useEffect(() => {
    const unregister = registerDirtyCheck({
      check: () => isActive && isDirtyRef.current,
      saveAndExit: onSaveRef.current ? () => onSaveRef.current!() : undefined,
      exitWithoutSaving: () => {
        isDirtyRef.current = false
        unregisterRef.current?.()
        unregisterRef.current = null
        onDiscardRef.current?.()
      },
      title,
      body,
      saveLabel,
    })
    unregisterRef.current = unregister
    return () => {
      unregisterRef.current = null
      unregister()
    }
  }, [registerDirtyCheck, isActive, title, body, saveLabel])

  const dismiss = useCallback(() => {
    unregisterRef.current?.()
    unregisterRef.current = null
  }, [])

  return { dismiss }
}
