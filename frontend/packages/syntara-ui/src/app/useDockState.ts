import globalBreakpointLg from '@patternfly/react-tokens/dist/esm/t_global_breakpoint_lg'
import { createContext, use, useCallback, useEffect, useMemo, useRef, useState } from 'react'

export type DockState = {
  isDockExpanded: boolean
  isDockTextExpanded: boolean
  isMobile: boolean
  dockedToggleRef: React.RefObject<HTMLButtonElement | null>
  mobileToggleRef: React.RefObject<HTMLButtonElement | null>
  onToggleDock: () => void
  onMobileToggle: () => void
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
const DOCK_STATE_STORAGE_KEY = 'syntara-nav-dock-state'

/** Delay before transferring focus between mobile and docked toggle buttons,
 *  allowing PF's CSS transition to complete so the target element is visible. */
const FOCUS_TRANSFER_DELAY_MS = 200

type PersistedDockState = {
  isDockExpanded: boolean
  isDockTextExpanded: boolean
}

function readPersistedDockState(): PersistedDockState {
  try {
    const raw = sessionStorage.getItem(DOCK_STATE_STORAGE_KEY)
    if (!raw) {
      return { isDockExpanded: false, isDockTextExpanded: false }
    }
    const parsed = JSON.parse(raw) as Partial<PersistedDockState>
    return {
      isDockExpanded: parsed.isDockExpanded === true,
      isDockTextExpanded: parsed.isDockTextExpanded === true,
    }
  } catch {
    return { isDockExpanded: false, isDockTextExpanded: false }
  }
}

function writePersistedDockState(state: PersistedDockState) {
  try {
    sessionStorage.setItem(DOCK_STATE_STORAGE_KEY, JSON.stringify(state))
  } catch {
    // sessionStorage may be unavailable in private browsing or restricted embeds.
  }
}

export function useDockStateProvider(): DockState {
  const [isDockExpanded, setIsDockExpanded] = useState(() => readPersistedDockState().isDockExpanded)
  const [isDockTextExpanded, setIsDockTextExpanded] = useState(() => readPersistedDockState().isDockTextExpanded)
  const [isMobile, setIsMobile] = useState(() =>
    typeof window.matchMedia === 'function'
      ? window.matchMedia(`(max-width: ${DOCK_DESKTOP_BREAKPOINT_PX}px)`).matches
      : false
  )
  const dockedToggleRef = useRef<HTMLButtonElement>(null)
  const mobileToggleRef = useRef<HTMLButtonElement>(null)
  const focusTimerRef = useRef<ReturnType<typeof setTimeout>>(undefined)
  const isDockExpandedRef = useRef(isDockExpanded)
  const isDockTextExpandedRef = useRef(isDockTextExpanded)

  useEffect(() => () => clearTimeout(focusTimerRef.current), [])

  useEffect(() => {
    isDockExpandedRef.current = isDockExpanded
    isDockTextExpandedRef.current = isDockTextExpanded
  }, [isDockExpanded, isDockTextExpanded])

  useEffect(() => {
    writePersistedDockState({ isDockExpanded, isDockTextExpanded })
  }, [isDockExpanded, isDockTextExpanded])

  useEffect(() => {
    if (typeof window.matchMedia !== 'function') return
    const mq = window.matchMedia(`(max-width: ${DOCK_DESKTOP_BREAKPOINT_PX}px)`)
    let wasMobile = mq.matches

    const handler = (e: MediaQueryListEvent) => {
      const nowMobile = e.matches
      if (wasMobile === nowMobile) {
        setIsMobile(nowMobile)
        return
      }

      if (nowMobile) {
        if (isDockTextExpandedRef.current && !isDockExpandedRef.current) {
          setIsDockExpanded(true)
        }
      } else if (isDockExpandedRef.current) {
        setIsDockTextExpanded(true)
        setIsDockExpanded(false)
      }

      wasMobile = nowMobile
      setIsMobile(nowMobile)
    }

    mq.addEventListener('change', handler)
    return () => mq.removeEventListener('change', handler)
  }, [])

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
      setIsDockTextExpanded((prev) => !prev)
    }
  }, [isMobile])

  return useMemo(
    () => ({
      isDockExpanded,
      isDockTextExpanded,
      isMobile,
      dockedToggleRef,
      mobileToggleRef,
      onToggleDock,
      onMobileToggle,
    }),
    [isDockExpanded, isDockTextExpanded, isMobile, onToggleDock, onMobileToggle]
  )
}
