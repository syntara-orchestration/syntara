import { useEffect, useRef, type RefObject } from 'react'

const MENU_SELECTOR = '.pf-v6-c-menu'

/** Ignore chained window/ancestor scrolls briefly after a wheel/touch inside the menu. */
const SCROLL_CHAIN_IGNORE_MS = 150

/**
 * Opening a Select often scrolls the page/panel (menu positioning / scrollIntoView)
 * while focus is still on the toggle. Ignore those opens so the menu is not dismissed
 * before the user can interact.
 */
const OPEN_SCROLL_IGNORE_MS = 300

function isInsideMenu(target: EventTarget | null): boolean {
  return target instanceof Element && Boolean(target.closest(MENU_SELECTOR))
}

function isInsideSelectUi(target: EventTarget | null, anchor: HTMLElement | null): boolean {
  if (!(target instanceof Element)) return false
  if (isInsideMenu(target)) return true
  return Boolean(anchor?.contains(target))
}

/**
 * Closes a PatternFly Select when the user scrolls outside the open menu
 * (page, modal body, or other scroll parents). Scrolling inside the menu list
 * still works and does not dismiss the menu.
 *
 * Attach the returned ref to a wrapper around the Select (the menu is portaled
 * to `document.body`, so ancestors of this wrapper are the scroll parents that
 * matter for dismiss-on-outer-scroll). Prefer `SynSelect`, which wires this for you.
 */
export function useCloseSelectOnOuterScroll(isOpen: boolean, onClose: () => void): RefObject<HTMLDivElement | null> {
  const anchorRef = useRef<HTMLDivElement | null>(null)
  const onCloseRef = useRef(onClose)
  const ignoreScrollUntilRef = useRef(0)

  useEffect(() => {
    onCloseRef.current = onClose
  }, [onClose])

  useEffect(() => {
    if (!isOpen) return

    ignoreScrollUntilRef.current = performance.now() + OPEN_SCROLL_IGNORE_MS

    const close = () => {
      onCloseRef.current()
    }

    const onWheelOrTouch = (event: Event) => {
      if (isInsideSelectUi(event.target, anchorRef.current)) {
        // Menu wheel can scroll-chain to the page; don't treat that as an outer dismiss.
        ignoreScrollUntilRef.current = performance.now() + SCROLL_CHAIN_IGNORE_MS
        return
      }
      close()
    }

    const onScroll = (event: Event) => {
      if (isInsideSelectUi(event.target, anchorRef.current)) return
      // Keyboard focus / arrowing options calls scrollIntoView on the page.
      // Opening the menu can also scroll while focus is still on the toggle.
      if (isInsideSelectUi(document.activeElement, anchorRef.current)) return
      if (performance.now() < ignoreScrollUntilRef.current) return
      close()
    }

    const attached = new Set<Element>()
    let parent = anchorRef.current?.parentElement ?? null
    while (parent) {
      const isScrollable = parent.scrollHeight > parent.clientHeight || parent.scrollWidth > parent.clientWidth
      if (isScrollable) {
        parent.addEventListener('scroll', onScroll, { passive: true })
        attached.add(parent)
      }
      parent = parent.parentElement
    }

    window.addEventListener('scroll', onScroll, { passive: true, capture: true })
    document.addEventListener('wheel', onWheelOrTouch, { passive: true, capture: true })
    document.addEventListener('touchmove', onWheelOrTouch, { passive: true, capture: true })

    return () => {
      attached.forEach((el) => {
        el.removeEventListener('scroll', onScroll)
      })
      window.removeEventListener('scroll', onScroll, true)
      document.removeEventListener('wheel', onWheelOrTouch, true)
      document.removeEventListener('touchmove', onWheelOrTouch, true)
    }
  }, [isOpen])

  return anchorRef
}
