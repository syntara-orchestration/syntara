import globalBreakpointLg from '@patternfly/react-tokens/dist/esm/t_global_breakpoint_lg'
import { createContext, use, useCallback, useEffect, useMemo, useRef, useState } from 'react'

export type DockState = {
  isDockExpanded: boolean
  isDockTextExpanded: boolean
  isDockExpandableExpanded: boolean
  isMobile: boolean
  dockedToggleRef: React.RefObject<HTMLButtonElement | null>
  mobileToggleRef: React.RefObject<HTMLButtonElement | null>
  onToggleDock: () => void
  onMobileToggle: () => void
  onNavToggle: (
    event: React.MouseEvent<HTMLButtonElement>,
    result: { groupId: number | string; isExpanded: boolean }
  ) => void
  onNavSelect: () => void
}

export const DockStateContext = createContext<DockState | null>(null)

export function useDockState(): DockState {
  const ctx = use(DockStateContext)
  if (!ctx) throw new Error('useDockState must be used within AppShell')
  return ctx
}

/**
 * Manages responsive dock expansion state following the PatternFly Compass
 * docked-nav pattern. On desktop the hamburger toggles `isDockTextExpanded`
 * (icon-only ↔ icon+text). On mobile it toggles `isDockExpanded` (hidden ↔
 * overlay). Focus is transferred between the mobile and docked toggle buttons
 * on open/close to maintain keyboard flow.
 */
const DOCK_DESKTOP_BREAKPOINT_PX = Number.parseInt(globalBreakpointLg.value) * 16

/** Delay before transferring focus between mobile and docked toggle buttons,
 *  allowing PF's CSS transition to complete so the target element is visible. */
const FOCUS_TRANSFER_DELAY_MS = 200

export function useDockStateProvider(): DockState {
  const [isDockExpanded, setIsDockExpanded] = useState(false)
  const [isDockTextExpanded, setIsDockTextExpanded] = useState(false)
  const [isDockExpandableExpanded, setIsDockExpandableExpanded] = useState(false)
  const [isMobile, setIsMobile] = useState(() =>
    typeof window.matchMedia === 'function'
      ? window.matchMedia(`(max-width: ${DOCK_DESKTOP_BREAKPOINT_PX}px)`).matches
      : false
  )
  const dockedToggleRef = useRef<HTMLButtonElement>(null)
  const mobileToggleRef = useRef<HTMLButtonElement>(null)
  const focusTimerRef = useRef<ReturnType<typeof setTimeout>>(undefined)

  useEffect(() => () => clearTimeout(focusTimerRef.current), [])

  useEffect(() => {
    if (typeof window.matchMedia !== 'function') return
    const mq = window.matchMedia(`(max-width: ${DOCK_DESKTOP_BREAKPOINT_PX}px)`)
    const handler = (e: MediaQueryListEvent) => setIsMobile(e.matches)
    mq.addEventListener('change', handler)
    return () => mq.removeEventListener('change', handler)
  }, [])

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if ((!isMobile && !isDockExpandableExpanded) || (isMobile && !isDockExpanded)) return
      const docked = document.getElementById('docked-masthead')
      const mobileTog = document.getElementById('mobile-masthead-toggle')
      if (docked && !docked.contains(event.target as Node) && !mobileTog?.contains(event.target as Node)) {
        setIsDockExpandableExpanded(false)
        setIsDockExpanded(false)
      }
    }
    const handleKeydown = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && (isDockExpandableExpanded || isDockExpanded)) {
        setIsDockExpandableExpanded(false)
        setIsDockExpanded(false)
      }
    }
    window.addEventListener('click', handleClickOutside)
    window.addEventListener('keydown', handleKeydown)
    return () => {
      window.removeEventListener('click', handleClickOutside)
      window.removeEventListener('keydown', handleKeydown)
    }
  }, [isDockExpandableExpanded, isDockExpanded, isMobile])

  const onMobileToggle = useCallback(() => {
    setIsDockExpanded((prev) => !prev)
    focusTimerRef.current = setTimeout(() => dockedToggleRef.current?.focus(), FOCUS_TRANSFER_DELAY_MS)
  }, [])

  const onToggleDock = useCallback(() => {
    if (isMobile) {
      setIsDockExpanded((prev) => {
        if (prev) focusTimerRef.current = setTimeout(() => mobileToggleRef.current?.focus(), FOCUS_TRANSFER_DELAY_MS)
        return !prev
      })
    } else {
      const nextTextExpanded = !isDockTextExpanded
      setIsDockTextExpanded(nextTextExpanded)
      if (!nextTextExpanded) setIsDockExpandableExpanded(false)
      if (isDockExpandableExpanded) {
        setIsDockExpandableExpanded(false)
        setIsDockTextExpanded(false)
      }
    }
  }, [isMobile, isDockTextExpanded, isDockExpandableExpanded])

  const onNavToggle: DockState['onNavToggle'] = useCallback(() => {
    if (!isMobile && !isDockExpandableExpanded && !isDockTextExpanded) {
      setIsDockExpandableExpanded(true)
    }
  }, [isMobile, isDockExpandableExpanded, isDockTextExpanded])

  const onNavSelect = useCallback(() => {
    setIsDockExpandableExpanded(false)
    setIsDockTextExpanded(false)
    setIsDockExpanded(false)
  }, [])

  return useMemo(
    () => ({
      isDockExpanded,
      isDockTextExpanded,
      isDockExpandableExpanded,
      isMobile,
      dockedToggleRef,
      mobileToggleRef,
      onToggleDock,
      onMobileToggle,
      onNavToggle,
      onNavSelect,
    }),
    [
      isDockExpanded,
      isDockTextExpanded,
      isDockExpandableExpanded,
      isMobile,
      onToggleDock,
      onMobileToggle,
      onNavToggle,
      onNavSelect,
    ]
  )
}
