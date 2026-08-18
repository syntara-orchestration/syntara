import { useCallback, useRef, useState } from 'react'

const DEFAULTS_3 = [33.3, 33.3, 33.4]
const DEFAULTS_2 = [33.3, 100 - 33.3]
const MIN_WIDTH = 15
const STORAGE_PREFIX = 'syntara-panel-sizes-'

function getStorageKey(workflowId: string, nodeId: string): string {
  return `${STORAGE_PREFIX}${workflowId}-${nodeId}`
}

function readSavedWidths(
  workflowId: string | undefined,
  nodeId: string | undefined,
  panelCount: 2 | 3
): number[] | null {
  if (!workflowId || !nodeId) return null
  try {
    const raw = localStorage.getItem(getStorageKey(workflowId, nodeId))
    if (!raw) return null
    const parsed: unknown = JSON.parse(raw)
    if (!Array.isArray(parsed) || parsed.length !== panelCount) return null
    if (!parsed.every((v): v is number => typeof v === 'number' && v >= MIN_WIDTH)) return null
    return parsed
  } catch {
    return null
  }
}

function saveWidths(workflowId: string | undefined, nodeId: string | undefined, widths: number[]): void {
  if (!workflowId || !nodeId) return
  try {
    localStorage.setItem(getStorageKey(workflowId, nodeId), JSON.stringify(widths))
  } catch {
    // localStorage full or unavailable — silently ignore
  }
}

function getDefaults(panelCount: 2 | 3): number[] {
  return panelCount === 3 ? [...DEFAULTS_3] : [...DEFAULTS_2]
}

export function useResizablePanels({
  panelCount,
  workflowId,
  nodeId,
}: {
  panelCount: 2 | 3
  workflowId: string | undefined
  nodeId: string | undefined
}) {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const containerWidthRef = useRef<number>(0)

  const identityKey = `${panelCount}-${workflowId ?? ''}-${nodeId ?? ''}`
  const [prevIdentityKey, setPrevIdentityKey] = useState(identityKey)

  const [widths, setWidths] = useState<number[]>(() => {
    return readSavedWidths(workflowId, nodeId, panelCount) ?? getDefaults(panelCount)
  })

  if (identityKey !== prevIdentityKey) {
    setPrevIdentityKey(identityKey)
    setWidths(readSavedWidths(workflowId, nodeId, panelCount) ?? getDefaults(panelCount))
  }

  const handleResize = useCallback((dividerIndex: number, deltaX: number) => {
    if (!containerRef.current) return

    if (containerWidthRef.current === 0) {
      containerWidthRef.current = containerRef.current.getBoundingClientRect().width
    }

    const containerWidth = containerWidthRef.current
    if (containerWidth === 0) return

    const deltaPercent = (deltaX / containerWidth) * 100

    setWidths((prev) => {
      const next = [...prev]

      let newLeft = next[dividerIndex] + deltaPercent
      let newRight = next[dividerIndex + 1] - deltaPercent

      if (newLeft < MIN_WIDTH) {
        newRight -= MIN_WIDTH - newLeft
        newLeft = MIN_WIDTH
      }
      if (newRight < MIN_WIDTH) {
        newLeft -= MIN_WIDTH - newRight
        newRight = MIN_WIDTH
      }

      next[dividerIndex] = newLeft
      next[dividerIndex + 1] = newRight
      return next
    })
  }, [])

  const handleResizeEnd = useCallback(() => {
    containerWidthRef.current = 0
    setWidths((current) => {
      saveWidths(workflowId, nodeId, current)
      return current
    })
  }, [workflowId, nodeId])

  return { widths, handleResize, handleResizeEnd, containerRef }
}
