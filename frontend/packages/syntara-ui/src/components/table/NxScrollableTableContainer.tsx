import { Stack, StackItem } from '@patternfly/react-core'
import { Caption, Table, type TableProps } from '@patternfly/react-table'
import type { ReactNode } from 'react'

import { NxPanel } from '../layout/NxPanel'

import styles from './NxScrollableTableContainer.module.css'
import { PaginationFooter, type PaginationFooterProps } from './PaginationFooter'
import { useScrollOverflow } from './useScrollOverflow'

/** Footer props passed to {@link NxScrollableTableContainer}. Forwarded directly to {@link PaginationFooter}. */
export type TableFooterProps = PaginationFooterProps

type NxScrollableTableContainerProps = {
  /** The table content (Thead, Tbody, etc.) */
  children: ReactNode
  /** Pagination footer props — always renders {@link PaginationFooter} when provided. */
  footer?: TableFooterProps
  /** Accessible caption for the table — rendered as a visually hidden `<caption>` element (W3C recommended). */
  caption: string
  /** Whether the table is expandable (affects table layout) */
  isExpandable?: boolean
  /** Opt out of fixed table layout when not expandable */
  useFixedLayout?: boolean
  /** PatternFly table density. Use `compact` for dense tables in tight panels. */
  variant?: TableProps['variant']
}

/**
 * A reusable container component for scrollable tables with sticky headers.
 * Provides consistent styling and layout for tables across the application.
 *
 * The root node is a PatternFly `StackItem` (`isFilled`). It must be a **direct** child of `Stack`;
 * wrapping it in another `StackItem` breaks flex layout (the table will not fill the panel height).
 */
export function NxScrollableTableContainer({
  children,
  footer,
  caption,
  isExpandable,
  useFixedLayout = true,
  variant,
}: NxScrollableTableContainerProps) {
  const useFixed = !isExpandable && useFixedLayout
  const { scrollRef, wrapperRef } = useScrollOverflow()
  const tableClassName = useFixed ? `${styles.table} ${styles.tableFixedLayout}` : styles.table
  return (
    <StackItem isFilled data-testid="scrollable-table-container-root" className={styles.root}>
      <NxPanel hasNoPadding isFullHeight isScrollable className={styles.panel}>
        <Stack className={styles.shellStack}>
          <div
            ref={wrapperRef}
            className={`${styles.scrollWrapper}${footer ? ` ${styles.scrollWrapperHasFooter}` : ''}`}
          >
            <div
              className={styles.scrollContainer}
              ref={scrollRef}
              tabIndex={0}
              role="region"
              aria-label={caption}
              data-testid="scroll-container"
            >
              <Table isPlain isStickyHeader isExpandable={isExpandable} variant={variant} className={tableClassName}>
                <Caption className="pf-v6-u-screen-reader">{caption}</Caption>
                {children}
              </Table>
            </div>
          </div>
          {footer && (
            <StackItem className={styles.footer}>
              <PaginationFooter {...footer} />
            </StackItem>
          )}
        </Stack>
      </NxPanel>
    </StackItem>
  )
}
