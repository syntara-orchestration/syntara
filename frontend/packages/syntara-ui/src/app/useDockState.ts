import globalBreakpointLg from '@patternfly/react-tokens/dist/esm/t_global_breakpoint_lg'
import { createContext, use, useCallback, useEffect, useMemo, useRef, useState } from 'react'

export type DockState = {
  isDockExpanded: boolean
  isDockTextExpanded: boolean
  isDockExpandableExpanded: boolean
  isMobile: boolean
  dockedToggleRef: React.RefObject<HTMLButtonElement | null>
  mobileToggleRef: React.RefObject<HTMLButtonElement | null>
  isNavGroupExpanded: (groupId: string) => boolean
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

function readIsMobileViewport(): boolean {
  return typeof window.matchMedia === 'function'
    ? window.matchMedia(`(max-width: ${DOCK_DESKTOP_BREAKPOINT_PX}px)`).matches
    : false
}

function readInitialDockState(): PersistedDockState & { isMobile: boolean } {
  const { isDockExpanded, isDockTextExpanded } = readPersistedDockState()
  const isMobile = readIsMobileViewport()

  if (!isMobile && isDockExpanded && !isDockTextExpanded) {
    return { isDockExpanded: false, isDockTextExpanded: true, isMobile }
  }

  return { isDockExpanded, isDockTextExpanded, isMobile }
}

function writePersistedDockState(state: PersistedDockState) {
  try {
    sessionStorage.setItem(DOCK_STATE_STORAGE_KEY, JSON.stringify(state))
  } catch {
    // sessionStorage may be unavailable in private browsing or restricted embeds.
  }
}

export function useDockStateProvider(): DockState {
  const [initialDockState] = useState(readInitialDockState)
  const [isDockExpanded, setIsDockExpanded] = useState(initialDockState.isDockExpanded)
  const [isDockTextExpanded, setIsDockTextExpanded] = useState(initialDockState.isDockTextExpanded)
  const [isDockExpandableExpanded, setIsDockExpandableExpanded] = useState(false)
  const [navGroupExpanded, setNavGroupExpanded] = useState<Record<string, boolean>>({})
  const [isMobile, setIsMobile] = useState(initialDockState.isMobile)
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
      if (wasMobile === nowMobile) return

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

  const isNavGroupExpanded = useCallback((groupId: string) => navGroupExpanded[groupId] ?? false, [navGroupExpanded])

  const onNavToggle: DockState['onNavToggle'] = useCallback(
    (_event, result) => {
      const groupId = String(result.groupId)
      setNavGroupExpanded((prev) => ({ ...prev, [groupId]: result.isExpanded }))

      if (!isMobile) {
        if (!isDockExpandableExpanded && !isDockTextExpanded) {
          setIsDockExpandableExpanded(true)
        }

        if (!isDockTextExpanded) {
          setIsDockTextExpanded(false)
        }
      }
    },
    [isMobile, isDockExpandableExpanded, isDockTextExpanded]
  )

  const onNavSelect = useCallback(() => {
    setNavGroupExpanded({})
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
      isNavGroupExpanded,
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
      isNavGroupExpanded,
      onToggleDock,
      onMobileToggle,
      onNavToggle,
      onNavSelect,
    ]
  )
}
