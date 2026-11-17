import { keepPreviousData } from '@tanstack/react-query'
import { useCallback, useMemo, useState } from 'react'

import { accessClient } from '../routes/access/accessClient'
import type { ProjectRead } from '../routes/access/types'

import { useDebouncedValue } from './useDebouncedValue'

/** Page size of the project picker's first page; reuse it to share that page's cache entry. */
export const PROJECTS_PAGE_SIZE = 20

export function usePaginatedProjects() {
  const [filterValue, setFilterValue] = useState('')
  const [cursor, setCursor] = useState<string | null>(null)
  const [extraPages, setExtraPages] = useState<ProjectRead[]>([])

  const debouncedFilter = useDebouncedValue(filterValue)

  const updateFilter = (val: string) => {
    setFilterValue(val)
    setCursor(null)
    setExtraPages([])
  }

  const resetPagination = () => {
    setFilterValue('')
    setCursor(null)
    setExtraPages([])
  }

  /** Clears typeahead text only; keeps cursor/extra pages so selections from later pages stay valid. */
  const clearTypeaheadOnly = useCallback(() => {
    setFilterValue('')
  }, [])

  const query = accessClient.useQuery(
    'get',
    '/projects',
    {
      params: {
        query: {
          limit: PROJECTS_PAGE_SIZE,
          ...(debouncedFilter ? { 'name[contains]': debouncedFilter } : {}),
          ...(cursor ? { cursor } : {}),
        },
      },
    },
    {
      // Keep the previous page's data visible while a new filter/cursor query is in flight.
      // Without this, `query.data` briefly becomes undefined on each keystroke, which
      // causes `selectedProject` to become null and makes the workflow page flash a
      // loading/error state while the user is typing in the project selector.
      placeholderData: keepPreviousData,
    }
  )

  const firstPageProjects = useMemo(() => query.data?.resources ?? [], [query.data])

  const projects = useMemo(() => {
    if (extraPages.length === 0) return firstPageProjects
    const allItems = [...extraPages, ...firstPageProjects]
    const seen = new Set<string | undefined>()
    return allItems.filter((p) => {
      if (seen.has(p.id)) return false
      seen.add(p.id)
      return true
    })
  }, [firstPageProjects, extraPages])

  const hasMore = !!query.data?.next
  const isLoadingMore = !!cursor && query.isFetching
  const isInitialPage = !cursor && !debouncedFilter

  const loadMore = useCallback(() => {
    const nextCursor = query.data?.next
    if (nextCursor) {
      setExtraPages(projects)
      setCursor(nextCursor)
    }
  }, [query.data?.next, projects])

  return {
    projects,
    filterValue,
    debouncedFilter,
    updateFilter,
    resetPagination,
    clearTypeaheadOnly,
    hasMore,
    isLoadingMore,
    isInitialPage,
    loadMore,
    query,
  }
}
