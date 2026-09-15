import { useCallback, useState } from 'react'

export type DialogState<T> = {
  /** Whether the dialog is open */
  isOpen: boolean
  /** The item associated with the open dialog (null when closed) */
  item: T | null
  /** Open the dialog with an associated item */
  open: (item: T) => void
  /** Close the dialog and clear the item */
  close: () => void
}

/**
 * Manages a dialog's open/close state along with an associated item.
 *
 * Replaces the repeated pattern of:
 * - `deleteDialogOpen: boolean` + `itemToDelete: T | null`
 * - `OPEN_DELETE_DIALOG` + `CLOSE_DELETE_DIALOG` reducer actions
 *
 * @example
 * ```tsx
 * const deleteDialog = useDialogState<User>()
 *
 * // Open with item:
 * deleteDialog.open(user)
 *
 * // In JSX:
 * <SynConfirmationDialog
 *   isOpen={deleteDialog.isOpen}
 *   onClose={deleteDialog.close}
 *   onConfirm={() => handleDelete(deleteDialog.item)}
 *   title="Delete user"
 * >
 *   Are you sure you want to delete "{deleteDialog.item?.name}"?
 * </SynConfirmationDialog>
 * ```
 */
export function useDialogState<T>(): DialogState<T> {
  const [isOpen, setIsOpen] = useState(false)
  const [item, setItem] = useState<T | null>(null)

  const open = useCallback((newItem: T) => {
    // Blur the trigger element before React re-renders with the dialog open.
    // PF Modal sets aria-hidden on #root in a child layout effect; blurring
    // here (synchronously during the event handler) ensures no element inside
    // #root retains focus when aria-hidden is applied.
    ;(document.activeElement as HTMLElement | null)?.blur?.()
    setItem(newItem)
    setIsOpen(true)
  }, [])

  const close = useCallback(() => {
    setIsOpen(false)
    setItem(null)
  }, [])

  return { isOpen, item, open, close }
}
