import { useCallback, useState } from 'react'

export function useExpandableRowIds(rowIds: string[]) {
  const [expandedRows, setExpandedRows] = useState<Set<string>>(new Set())

  const allRowsExpanded = rowIds.length > 0 && rowIds.every((id) => expandedRows.has(id))

  const handleToggleRow = useCallback((rowId: string) => {
    setExpandedRows((prev) => {
      const next = new Set(prev)
      if (next.has(rowId)) {
        next.delete(rowId)
      } else {
        next.add(rowId)
      }
      return next
    })
  }, [])

  const handleCollapseAll = useCallback(() => {
    if (allRowsExpanded) {
      setExpandedRows(new Set())
    } else {
      setExpandedRows(new Set(rowIds))
    }
  }, [allRowsExpanded, rowIds])

  return {
    expandedRows,
    allRowsExpanded,
    handleToggleRow,
    handleCollapseAll,
  }
}
