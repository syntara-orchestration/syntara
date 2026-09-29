import { Pagination, type PaginationProps } from '@patternfly/react-core'

/** Props for the global {@link PaginationFooter} component */
export type PaginationFooterProps = Required<Pick<PaginationProps, 'page' | 'perPage'>> & {
  /**
   * Total item count returned by the API. Forwarded as `itemCount` to the PatternFly
   * `Pagination` component. When omitted or `null`, the count is estimated from `page`,
   * `perPage`, and `hasNext` so next/prev controls render correctly.
   */
  total?: PaginationProps['itemCount'] | null
  /** Whether a next page exists. Used for itemCount estimation when `total` is unknown. */
  hasNext: boolean
  /** Called when the user navigates to the previous page. */
  onPrev: () => void
  /** Called when the user navigates to the next page. */
  onNext: () => void
  /** Called with the newly selected per-page value when the user changes the page size. */
  onPerPageChange: (perPage: number) => void
}

/**
 * A compact, bottom-aligned PatternFly pagination control for list pages.
 *
 * Pair with `useCursorPagination` (cursor-based APIs) or `useClientPagination`
 * (in-memory datasets filtered/sorted in the browser).
 *
 * When the API returns a known `total`, pass it directly. When the total is
 * unavailable (cursor-based APIs), omit it or pass `null` — the component
 * estimates an `itemCount` that keeps the PatternFly next/prev buttons enabled
 * or disabled correctly based on `hasNext`.
 */
export function PaginationFooter({
  page,
  perPage,
  total,
  hasNext,
  onPrev,
  onNext,
  onPerPageChange,
}: Readonly<PaginationFooterProps>) {
  // +1 signals to PF that another page exists without knowing the exact total.
  const estimatedItemCount = hasNext ? page * perPage + 1 : page * perPage
  const itemCount = total ?? estimatedItemCount

  return (
    <Pagination
      itemCount={itemCount}
      page={page}
      perPage={perPage}
      onSetPage={(_event, newPage) => {
        if (newPage > page) onNext()
        else onPrev()
      }}
      onPerPageSelect={(_event, newPerPage) => onPerPageChange(newPerPage)}
      variant="bottom"
      isCompact
    />
  )
}
