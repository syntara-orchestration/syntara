import globalBreakpointLg from '@patternfly/react-tokens/dist/esm/t_global_breakpoint_lg'
import { createContext, use, useCallback, useEffect, useMemo, useRef, useState } from 'react'

export type DockState = {
  isDockExpanded: boolean
  isDockOverlay: boolean
  isMobile: boolean
  dockedToggleRef: React.RefObject<HTMLButtonElement | null>
  mobileToggleRef: React.RefObject<HTMLButtonElement | null>
  isNavGroupExpanded: (groupId: string) => boolean
  onToggleDock: () => void
  onMobileToggle: () => void
  onExpandNavGroup: (event: React.MouseEvent<HTMLButtonElement>, groupId: string, isExpanded: boolean) => void
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
 * docked-nav pattern. `isDockExpanded` controls icon-only vs icon+text on
 * desktop and visibility on mobile. `isDockOverlay` expands the dock over
 * content when opening a nav group from the collapsed dock.
 */
const DOCK_DESKTOP_BREAKPOINT_PX = Number.parseInt(globalBreakpointLg.value) * 16
const DOCK_STATE_STORAGE_KEY = 'syntara-nav-dock-state'

/** Delay before transferring focus between mobile and docked toggle buttons,
 *  allowing PF's CSS transition to complete so the target element is visible. */
const FOCUS_TRANSFER_DELAY_MS = 200

type PersistedDockState = {
  isDockExpanded: boolean
}

function readPersistedDockState(): PersistedDockState {
  try {
    const raw = sessionStorage.getItem(DOCK_STATE_STORAGE_KEY)
    if (!raw) {
      return { isDockExpanded: false }
    }
    const parsed = JSON.parse(raw) as Partial<PersistedDockState & { isDockTextExpanded?: boolean }>
    return {
      isDockExpanded: parsed.isDockExpanded === true || parsed.isDockTextExpanded === true,
    }
  } catch {
    return { isDockExpanded: false }
  }
}

function readIsMobileViewport(): boolean {
  return typeof window.matchMedia === 'function'
    ? window.matchMedia(`(max-width: ${DOCK_DESKTOP_BREAKPOINT_PX}px)`).matches
    : false
}

function readInitialDockState(): PersistedDockState & { isMobile: boolean } {
  const { isDockExpanded } = readPersistedDockState()
  const isMobile = readIsMobileViewport()

  return {
    isDockExpanded: isMobile ? false : isDockExpanded,
    isMobile,
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
  const [initialDockState] = useState(readInitialDockState)
  const [isDockExpanded, setIsDockExpanded] = useState(initialDockState.isDockExpanded)
  const [isDockOverlay, setIsDockOverlay] = useState(false)
  const [navGroupExpanded, setNavGroupExpanded] = useState<Record<string, boolean>>({})
  const [isMobile, setIsMobile] = useState(initialDockState.isMobile)
  const dockedToggleRef = useRef<HTMLButtonElement>(null)
  const mobileToggleRef = useRef<HTMLButtonElement>(null)
  const focusTimerRef = useRef<ReturnType<typeof setTimeout>>(undefined)

  useEffect(() => () => clearTimeout(focusTimerRef.current), [])

  const setDockExpanded = useCallback(
    (value: boolean | ((prev: boolean) => boolean)) => {
      setIsDockExpanded((prev) => {
        const next = typeof value === 'function' ? value(prev) : value
        if (!isMobile) {
          writePersistedDockState({ isDockExpanded: next })
        }
        return next
      })
    },
    [isMobile]
  )

  useEffect(() => {
    if (typeof window.matchMedia !== 'function') return
    const mq = window.matchMedia(`(max-width: ${DOCK_DESKTOP_BREAKPOINT_PX}px)`)
    let wasMobile = mq.matches

    const handler = (e: MediaQueryListEvent) => {
      const nowMobile = e.matches
      if (wasMobile === nowMobile) return

      wasMobile = nowMobile
      setIsMobile(nowMobile)
      if (!nowMobile) {
        setIsDockExpanded((current) => {
          writePersistedDockState({ isDockExpanded: current })
          return current
        })
      }
    }

    mq.addEventListener('change', handler)
    return () => mq.removeEventListener('change', handler)
  }, [])

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (!isDockExpanded) return

      const docked = document.getElementById('docked-masthead')
      const mobileTog = document.getElementById('mobile-masthead-toggle')
      if (
        docked &&
        !docked.contains(event.target as Node) &&
        !mobileTog?.contains(event.target as Node) &&
        (isDockOverlay || isMobile)
      ) {
        setIsDockOverlay(false)
        setDockExpanded(false)
      }
    }
    const handleKeydown = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && isDockExpanded) {
        setIsDockOverlay(false)
        setDockExpanded(false)
      }
    }
    window.addEventListener('click', handleClickOutside)
    window.addEventListener('keydown', handleKeydown)
    return () => {
      window.removeEventListener('click', handleClickOutside)
      window.removeEventListener('keydown', handleKeydown)
    }
  }, [isDockExpanded, isDockOverlay, isMobile, setDockExpanded])

  const onMobileToggle = useCallback(() => {
    setDockExpanded((prev) => !prev)
    focusTimerRef.current = setTimeout(() => dockedToggleRef.current?.focus(), FOCUS_TRANSFER_DELAY_MS)
  }, [setDockExpanded])

  const onToggleDock = useCallback(() => {
    setDockExpanded((prev) => {
      const next = !prev
      if (!next) {
        setIsDockOverlay(false)
        if (isMobile) {
          focusTimerRef.current = setTimeout(() => mobileToggleRef.current?.focus(), FOCUS_TRANSFER_DELAY_MS)
        }
      }
      return next
    })
  }, [isMobile, setDockExpanded])

  const isNavGroupExpanded = useCallback((groupId: string) => navGroupExpanded[groupId] ?? false, [navGroupExpanded])

  const onExpandNavGroup: DockState['onExpandNavGroup'] = useCallback(
    (_event, groupId, isExpanded) => {
      if (!isDockExpanded) {
        setNavGroupExpanded((prev) => ({ ...prev, [groupId]: true }))
        setIsDockOverlay(true)
        setDockExpanded(true)
      } else {
        setNavGroupExpanded((prev) => ({ ...prev, [groupId]: isExpanded }))
      }
    },
    [isDockExpanded, setDockExpanded]
  )

  const onNavSelect = useCallback(() => {
    if (isDockExpanded && !isDockOverlay && !isMobile) {
      return
    }

    setIsDockOverlay(false)
    setDockExpanded(false)
  }, [isDockExpanded, isDockOverlay, isMobile, setDockExpanded])

  return useMemo(
    () => ({
      isDockExpanded,
      isDockOverlay,
      isMobile,
      dockedToggleRef,
      mobileToggleRef,
      isNavGroupExpanded,
      onToggleDock,
      onMobileToggle,
      onExpandNavGroup,
      onNavSelect,
    }),
    [
      isDockExpanded,
      isDockOverlay,
      isMobile,
      isNavGroupExpanded,
      onToggleDock,
      onMobileToggle,
      onExpandNavGroup,
      onNavSelect,
    ]
  )
}
