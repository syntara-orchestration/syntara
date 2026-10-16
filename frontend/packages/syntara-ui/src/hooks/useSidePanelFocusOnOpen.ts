import { useLayoutEffect, useRef, type RefObject } from 'react'

/**
 * Moves focus into a side panel when it opens and restores focus to the prior element on close.
 */
export function useSidePanelFocusOnOpen(isOpen: boolean, panelRootRef: RefObject<HTMLElement | null>): void {
  const previousFocusRef = useRef<Element | null>(null)

  useLayoutEffect(() => {
    if (!isOpen) {
      return undefined
    }

    previousFocusRef.current = document.activeElement

    const root = panelRootRef.current
    const closeButton = root?.querySelector<HTMLElement>('button[aria-label*="Close"]')
    const heading = root?.querySelector<HTMLElement>('h2')
    ;(closeButton ?? heading)?.focus()

    return () => {
      const previous = previousFocusRef.current
      if (previous instanceof HTMLElement && document.contains(previous)) {
        previous.focus()
      }
    }
  }, [isOpen, panelRootRef])
}
