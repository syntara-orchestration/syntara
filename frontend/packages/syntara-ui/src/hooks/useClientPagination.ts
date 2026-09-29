import { useCallback, useState } from 'react'

import type { PaginationFooterProps } from '../components/table/PaginationFooter'

type UseClientPaginationOptions = {
  /** Default page size (defaults to 20) */
  defaultPerPage?: number
}

export type UseClientPaginationResult = {
  /** Current page number (1-based) */
  page: number
  /** Current items per page */
  perPage: number
  /** Reset to page 1 (e.g. when filters or sort change) */
  resetPage: () => void
  /** Update page size and reset to page 1 */
  handlePerPageChange: (perPage: number) => void
  /** Return the current page slice of an in-memory array */
  paginate: <T>(items: readonly T[]) => T[]
  /** Build footer props for SynScrollableTableContainer / SynListPanelTable */
  getFooterProps: (total: number) => PaginationFooterProps
}

/**
 * Encapsulates client-side (in-memory) table pagination.
 *
 * Use for tables that load a full dataset then filter/sort/paginate locally.
 * For cursor-based API list pages, use {@link useCursorPagination} instead.
 */
export function useClientPagination(options: UseClientPaginationOptions = {}): UseClientPaginationResult {
  const { defaultPerPage = 20 } = options

  const [page, setPage] = useState(1)
  const [perPage, setPerPage] = useState(defaultPerPage)

  const resetPage = useCallback(() => {
    setPage(1)
  }, [])

  const handlePerPageChange = useCallback(
    (newPerPage: number) => {
      setPerPage(newPerPage)
      resetPage()
    },
    [resetPage]
  )

  const paginate = useCallback(
    <T>(items: readonly T[]): T[] => {
      const start = (page - 1) * perPage
      return items.slice(start, start + perPage)
    },
    [page, perPage]
  )

  const getFooterProps = useCallback(
    (total: number): PaginationFooterProps => ({
      page,
      perPage,
      total,
      hasNext: page * perPage < total,
      onPrev: () => setPage((currentPage) => Math.max(1, currentPage - 1)),
      onNext: () => setPage((currentPage) => currentPage + 1),
      onPerPageChange: handlePerPageChange,
    }),
    [page, perPage, handlePerPageChange]
  )

  return {
    page,
    perPage,
    resetPage,
    handlePerPageChange,
    paginate,
    getFooterProps,
  }
}
