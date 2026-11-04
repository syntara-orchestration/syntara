import { useEffect, useState } from 'react'

/**
 * Returns true only after `active` has stayed true for `delayMs`.
 * Hides immediately when `active` becomes false.
 */
export function useShowAfterDelay(active: boolean, delayMs: number): boolean {
  const [visible, setVisible] = useState(false)

  useEffect(() => {
    if (!active) {
      return undefined
    }

    const timer = window.setTimeout(() => setVisible(true), delayMs)

    return () => {
      window.clearTimeout(timer)
      setVisible(false)
    }
  }, [active, delayMs])

  return active && visible
}
