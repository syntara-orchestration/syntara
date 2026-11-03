import { useEffect } from 'react'

import { wrappedUndo, wrappedRedo } from '../../../stores/useWorkflowStore'

const EDITABLE_TAGS = new Set(['INPUT', 'TEXTAREA', 'SELECT'])
const EDITABLE_ROLES = new Set(['textbox', 'combobox', 'searchbox', 'spinbutton'])

function isEditableElement(element: Element | null): boolean {
  if (!element) return false
  if (EDITABLE_TAGS.has(element.tagName)) return true
  if (element instanceof HTMLElement && element.isContentEditable) return true
  const role = element.getAttribute('role')
  if (role && EDITABLE_ROLES.has(role)) return true
  return false
}

/**
 * Registers global keyboard shortcuts for undo (Ctrl/Cmd+Z) and
 * redo (Ctrl/Cmd+Shift+Z or Ctrl+Y).
 *
 * Shortcuts are suppressed when focus is inside editable elements
 * (inputs, textareas, contenteditable) or when the step editor overlay is open.
 */
export function useUndoRedoKeyboard({ disabled = false }: { disabled?: boolean } = {}) {
  useEffect(() => {
    if (disabled) return

    function handleKeyDown(event: KeyboardEvent) {
      const isMeta = event.metaKey || event.ctrlKey
      if (!isMeta) return

      if (isEditableElement(document.activeElement)) return

      const key = event.key.toLowerCase()
      if (key === 'z' && !event.shiftKey) {
        event.preventDefault()
        wrappedUndo()
      } else if ((key === 'z' && event.shiftKey) || (key === 'y' && !event.shiftKey)) {
        event.preventDefault()
        wrappedRedo()
      }
    }

    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [disabled])
}
