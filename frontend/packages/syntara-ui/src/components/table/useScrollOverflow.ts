import { useCallback, useRef } from 'react'

/** Used when the scroll element does not define `--syn-scroll-fade-distance`. */
const FALLBACK_FADE_DISTANCE_PX = 120

type ScrollOverflowRefs = {
  /** Callback ref for the overflowing scroll container. */
  scrollRef: (node: HTMLElement | null) => (() => void) | void
  /**
   * Callback ref for the element that receives `--syn-scroll-fade-opacity`; typically a wrapper
   * around the scroll container whose `::after` pseudo-element renders the gradient overlay.
   */
  wrapperRef: (node: HTMLElement | null) => (() => void) | void
}

/**
 * Drives a CSS bottom-fade effect that signals scrollable overflow.
 *
 * Sets `--syn-scroll-fade-opacity` on the wrapper element to a value between `0` (fully scrolled
 * down, no more content) and `1` (content below the fold). The fade-in distance is controlled by
 * the `--syn-scroll-fade-distance` CSS custom property on the scroll element; falls back to
 * `FALLBACK_FADE_DISTANCE_PX` if the property is absent or non-numeric.
 *
 * Uses React 19 ref callback cleanup functions to attach/detach scroll listeners and
 * `ResizeObserver` when the DOM nodes mount and unmount — no paired `useRef` + `useEffect`.
 * Callback refs are wrapped in `useCallback` so React does not tear down and re-attach listeners
 * on every parent re-render.
 *
 * @see https://react.dev/blog/2024/12/05/react-19#cleanup-functions-for-refs
 */
export function useScrollOverflow(): ScrollOverflowRefs {
  const nodesRef = useRef<{ scroll: HTMLElement | null; wrapper: HTMLElement | null }>({
    scroll: null,
    wrapper: null,
  })
  const fadeDistanceRef = useRef(FALLBACK_FADE_DISTANCE_PX)
  const teardownRef = useRef<(() => void) | null>(null)

  const sync = useCallback(() => {
    teardownRef.current?.()
    teardownRef.current = null

    const scrollNode = nodesRef.current.scroll
    const wrapperNode = nodesRef.current.wrapper
    if (!scrollNode || !wrapperNode) return

    // Locals with definite types so nested listeners keep narrowing under tsc.
    const scrollEl: HTMLElement = scrollNode
    const wrapperEl: HTMLElement = wrapperNode

    function readFadeDistance() {
      const raw = getComputedStyle(scrollEl).getPropertyValue('--syn-scroll-fade-distance').trim()
      const parsed = Number.parseFloat(raw)
      fadeDistanceRef.current = Number.isFinite(parsed) ? parsed : FALLBACK_FADE_DISTANCE_PX
    }

    function update() {
      if (scrollEl.scrollHeight <= scrollEl.clientHeight) {
        wrapperEl.style.setProperty('--syn-scroll-fade-opacity', '0')
        return
      }
      const scrollableRemaining = scrollEl.scrollHeight - scrollEl.scrollTop - scrollEl.clientHeight
      const t = Math.min(1, Math.max(0, scrollableRemaining / fadeDistanceRef.current))
      // Smoothstep easing: starts and ends gradually rather than dropping linearly.
      const opacity = t * t * (3 - 2 * t)
      wrapperEl.style.setProperty('--syn-scroll-fade-opacity', String(opacity))
      // Signal when fully scrolled to the bottom so CSS can suppress the doubled
      // border between the last table row and the pagination footer.
      if (scrollableRemaining < 1) {
        scrollEl.dataset.atBottom = ''
      } else {
        delete scrollEl.dataset.atBottom
      }
    }

    readFadeDistance()
    update()

    scrollEl.addEventListener('scroll', update, { passive: true })

    const resizeObserver = new ResizeObserver(() => {
      readFadeDistance()
      update()
    })
    resizeObserver.observe(scrollEl)

    teardownRef.current = () => {
      scrollEl.removeEventListener('scroll', update)
      resizeObserver.disconnect()
    }
  }, [])

  const scrollRef = useCallback(
    (node: HTMLElement | null) => {
      nodesRef.current.scroll = node
      sync()
      return () => {
        nodesRef.current.scroll = null
        teardownRef.current?.()
        teardownRef.current = null
      }
    },
    [sync]
  )

  const wrapperRef = useCallback(
    (node: HTMLElement | null) => {
      nodesRef.current.wrapper = node
      sync()
      return () => {
        nodesRef.current.wrapper = null
        teardownRef.current?.()
        teardownRef.current = null
      }
    },
    [sync]
  )

  return { scrollRef, wrapperRef }
}
