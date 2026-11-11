import { useCallback, useEffect, useRef, useState } from 'react'

export function useRunDetailsPanelExpand(
  panelHeight: number,
  setPanelHeight: (height: number) => void,
  enabled: boolean
) {
  const [isExpanded, setIsExpanded] = useState(false)
  const savedHeightRef = useRef(panelHeight)

  useEffect(() => {
    if (!isExpanded) {
      savedHeightRef.current = panelHeight
    }
  }, [panelHeight, isExpanded])

  const collapse = useCallback(() => {
    setIsExpanded(false)
    setPanelHeight(savedHeightRef.current)
  }, [setPanelHeight])

  const toggle = useCallback(() => {
    if (isExpanded) {
      collapse()
      return
    }
    savedHeightRef.current = panelHeight
    setIsExpanded(true)
  }, [collapse, isExpanded, panelHeight])

  useEffect(() => {
    if (!enabled || !isExpanded) {
      return
    }
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault()
        collapse()
      }
    }
    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [collapse, enabled, isExpanded])

  const active = enabled && isExpanded

  return {
    isPanelExpanded: active,
    panelExpandControl: enabled
      ? {
          isExpanded: active,
          onToggle: toggle,
        }
      : undefined,
  }
}
