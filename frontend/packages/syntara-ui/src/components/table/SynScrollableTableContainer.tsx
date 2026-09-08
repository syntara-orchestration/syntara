import { Stack, StackItem } from '@patternfly/react-core'
import { Caption, Table, type TableProps } from '@patternfly/react-table'
import type { ReactNode } from 'react'

import { SynPanel } from '../layout/SynPanel'

import { PaginationFooter, type PaginationFooterProps } from './PaginationFooter'
import styles from './SynScrollableTableContainer.module.css'
import { useScrollOverflow } from './useScrollOverflow'

/** Footer props passed to {@link SynScrollableTableContainer}. Forwarded directly to {@link PaginationFooter}. */
export type TableFooterProps = PaginationFooterProps

type SynScrollableTableContainerProps = {
  /** The table content (Thead, Tbody, etc.) */
  children: ReactNode
  /** Pagination footer props — always renders {@link PaginationFooter} when provided. */
  footer?: TableFooterProps
  /**
   * Custom footer pinned inside the panel (same slot as {@link PaginationFooter}).
   * Use when prev/next is not the standard page-size pagination, e.g. cursor-only APIs.
   * Ignored when `footer` is also set.
   */
  footerContent?: ReactNode
  /** Accessible caption for the table — rendered as a visually hidden `<caption>` element (W3C recommended). */
  caption: string
  /** Whether the table is expandable (affects table layout) */
  isExpandable?: boolean
  /** Opt out of fixed table layout when not expandable */
  useFixedLayout?: boolean
  /** PatternFly table density. Use `compact` for dense tables in tight panels. */
  variant?: TableProps['variant']
  /** Alternating row colors. Forwarded to PatternFly {@link Table}. */
  isStriped?: boolean
}

/**
 * A reusable container component for scrollable tables with sticky headers.
 * Provides consistent styling and layout for tables across the application.
 *
 * The root node is a PatternFly `StackItem` (`isFilled`). It must be a **direct** child of `Stack`;
 * wrapping it in another `StackItem` breaks flex layout (the table will not fill the panel height).
 */
export function SynScrollableTableContainer({
  children,
  footer,
  footerContent,
  caption,
  isExpandable,
  useFixedLayout = true,
  variant,
  isStriped,
}: SynScrollableTableContainerProps) {
  const useFixed = !isExpandable && useFixedLayout
  const { scrollRef, wrapperRef } = useScrollOverflow()
  const tableClassName = useFixed ? `${styles.table} ${styles.tableFixedLayout}` : styles.table
  const pinnedFooter = footer ? <PaginationFooter {...footer} /> : footerContent
  return (
    <StackItem isFilled data-testid="scrollable-table-container-root" className={styles.root}>
      <SynPanel hasNoPadding isFullHeight isScrollable className={styles.panel}>
        <Stack className={styles.shellStack}>
          <div
            ref={wrapperRef}
            className={`${styles.scrollWrapper}${pinnedFooter ? ` ${styles.scrollWrapperHasFooter}` : ''}`}
          >
            <div
              className={styles.scrollContainer}
              ref={scrollRef}
              tabIndex={0}
              role="region"
              aria-label={caption}
              data-testid="scroll-container"
            >
              <Table
                isPlain
                isStickyHeader
                isExpandable={isExpandable}
                isStriped={isStriped}
                variant={variant}
                className={tableClassName}
              >
                <Caption className="pf-v6-u-screen-reader">{caption}</Caption>
                {children}
              </Table>
            </div>
          </div>
          {pinnedFooter && <StackItem className={styles.footer}>{pinnedFooter}</StackItem>}
        </Stack>
      </SynPanel>
    </StackItem>
  )
}
