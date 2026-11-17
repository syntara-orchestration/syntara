import { useCallback, useMemo } from 'react'

type UseApprovalNavigationResult<T> = {
  /** The current item in the navigable list. */
  current: T | null
  /** The current index (0-based). */
  currentIndex: number
  /** Total number of approvals. */
  total: number
  /** Whether there is a previous approval to navigate to. */
  hasPrev: boolean
  /** Whether there is a next approval to navigate to. */
  hasNext: boolean
  /** Navigate to the previous approval. No-op if already at first. */
  navigatePrev: () => void
  /** Navigate to the next approval. No-op if already at last. */
  navigateNext: () => void
}

/**
 * Encapsulates approval navigation logic with bounds checking.
 * Provides prev/next handlers and flags for button disabled states.
 */
export function useApprovalNavigation<T>(
  currentIndex: number,
  onNavigate: (index: number) => void,
  approvals: readonly T[] = []
): UseApprovalNavigationResult<T> {
  const total = approvals.length
  const current = approvals[currentIndex] ?? null
  const hasPrev = currentIndex > 0
  const hasNext = currentIndex < total - 1

  const navigatePrev = useCallback(() => {
    if (hasPrev) {
      onNavigate(currentIndex - 1)
    }
  }, [hasPrev, currentIndex, onNavigate])

  const navigateNext = useCallback(() => {
    if (hasNext) {
      onNavigate(currentIndex + 1)
    }
  }, [hasNext, currentIndex, onNavigate])

  return useMemo(
    () => ({
      current,
      currentIndex,
      total,
      hasPrev,
      hasNext,
      navigatePrev,
      navigateNext,
    }),
    [current, currentIndex, total, hasPrev, hasNext, navigatePrev, navigateNext]
  )
}
