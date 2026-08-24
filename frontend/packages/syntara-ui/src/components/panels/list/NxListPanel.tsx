import { Skeleton, StackItem } from '@patternfly/react-core'
import type { TabsProps } from '@patternfly/react-core'
import { Tbody, Td, Tr } from '@patternfly/react-table'
import React, { createContext, use, useId, useMemo } from 'react'
import type { ReactNode } from 'react'

import type { FilterConfig, FilterFieldDefinition } from '../../../types/filters'
import { FilterBar } from '../../filters/FilterBar'
import { SynPanel } from '../../layout/SynPanel'
import { SynPanelContentStack } from '../../layout/SynPanelContentStack'
import { SynEmptyStateFilter } from '../../states/SynEmptyStateFilter'
import { SynEmptyStateNoData } from '../../states/SynEmptyStateNoData'
import { SynErrorState } from '../../states/SynErrorState'
import { SynLoadingState } from '../../states/SynLoadingState'
import { type TableFooterProps, NxScrollableTableContainer } from '../../table/NxScrollableTableContainer'
import { NxUrlTabs } from '../../tabs/NxUrlTabs'

import styles from './NxListPanel.module.css'

/**
 * Shared between `NxListPanelTabs` and `NxListPanelView`. Placed at `NxListPanel`
 * (not `NxListPanelTabs`) so `NxListPanelView` rendered via a TanStack Router `<Outlet>`
 * can still consume it as a descendant of `NxListPanel` but not of `NxListPanelTabs`.
 */
type NxListPanelTabContextValue = {
  /** Returns the stable DOM id to use as a tabpanel id for the given tab eventKey. */
  getPanelId: (eventKey: string) => string
}

const NxListPanelTabContext = createContext<NxListPanelTabContextValue | null>(null)

function useNxListPanelTabContext() {
  return use(NxListPanelTabContext)
}

export type NxListPanelProps = {
  children: ReactNode
}

/** Full-height scrollable list panel wrapper. */
export function NxListPanel({ children }: NxListPanelProps) {
  const uid = useId()
  const tabContextValue = useMemo<NxListPanelTabContextValue>(
    () => ({ getPanelId: (eventKey: string) => `${uid}-tab-panel-${eventKey}` }),
    [uid]
  )
  return (
    <NxListPanelTabContext.Provider value={tabContextValue}>
      <SynPanel isFullHeight>
        <SynPanelContentStack hasGutter>{children}</SynPanelContentStack>
      </SynPanel>
    </NxListPanelTabContext.Provider>
  )
}

export type NxListPanelViewProps = {
  /** Table and arbitrary content — shown only in the data state. */
  body: ReactNode

  /**
   * True on initial load (no cached data yet) — hides the toolbar and body and shows a
   * full-panel spinner. Wire to TanStack Query's `query.isPending`.
   *
   * Do NOT use `isFetching` here — that flag is also true during background refetches when data
   * is already on screen, and swapping to a spinner then would discard the visible table.
   */
  isPending: boolean
  /** Query error — shows error state when truthy. */
  error: unknown
  /** Called when the user clicks "Retry". */
  onRetry: () => void
  /** Override the error state heading. Defaults to the error's HTTP status phrase, or "Error" for plain JS errors. */
  errorTitle?: string

  /** True when the current data set has zero items. */
  isEmpty: boolean
  /** True when any filters are currently applied. */
  hasActiveFilters: boolean
  /** Called when the user clicks "Clear all filters". */
  onClearAllFilters: () => void
  /** Custom no-data empty state. Defaults to `SynEmptyStateNoData`. */
  noDataState?: ReactNode

  /**
   * Slot rendered above content; hidden during initial load (`isPending`).
   * Omit to suppress the toolbar entirely — useful for "no data yet" empty states
   * that should show a full-panel call-to-action rather than an empty filter bar.
   */
  toolbar?: ReactNode
  /**
   * Background refetch in progress — disables toolbar interaction while the body (the table)
   * continues to render. Wire to TanStack Query's `query.isFetching`.
   *
   * Consumers should swap `<Tbody>` for `<NxListPanelSkeletonTbody>` when this is true so rows
   * animate while the fresh data loads. Do NOT use this for the initial load — use `isPending`.
   */
  isFetching?: boolean

  /**
   * The `eventKey` of the tab this view belongs to (e.g. `"members"`).
   * Required when `NxListPanelView` is used inside a tabbed `NxListPanel`.
   * Pair with `tabLabel` — together they produce a `role="tabpanel"` wrapper whose
   * `id` is registered in `NxListPanelTabContext` and targeted by the tab's `aria-controls`.
   */
  tabKey?: string
  /**
   * Accessible name for the tab panel (e.g. `"Members"`).
   * Required when `tabKey` is set.
   *
   * `aria-label` is used instead of `aria-labelledby` because PF generates tab button IDs with
   * an internal random counter (`pf-tab-{eventKey}-{internalUid}`) that is not predictable or
   * controllable from outside PF, making `aria-labelledby` infeasible.
   */
  tabLabel?: string
}

/** @internal Renders the appropriate state slot for `NxListPanelView`. Not exported. */
function ListPanelStateContent({
  isPending,
  error,
  onRetry,
  errorTitle,
  isEmpty,
  hasActiveFilters,
  onClearAllFilters,
  noDataState,
}: Omit<NxListPanelViewProps, 'body' | 'toolbar'>) {
  if (isPending) return <SynLoadingState />
  if (error) return <SynErrorState title={errorTitle} message={error} onRetry={onRetry} />
  if (isEmpty && hasActiveFilters) return <SynEmptyStateFilter clearAllFilters={onClearAllFilters} />
  if (isEmpty) return noDataState ?? <SynEmptyStateNoData />
  return null
}

/** Drives loading/error/empty/data states for a list panel. Must be a direct child of `NxListPanel`. */
export function NxListPanelView({
  body,
  isPending,
  isFetching,
  error,
  onRetry,
  errorTitle,
  isEmpty,
  hasActiveFilters,
  onClearAllFilters,
  noDataState,
  toolbar,
  tabKey,
  tabLabel,
}: NxListPanelViewProps) {
  const showBody = !isPending && !error && !isEmpty
  const tabCtx = useNxListPanelTabContext()

  const content = (
    <>
      {!isPending && toolbar && (
        <StackItem>
          <fieldset
            disabled={isFetching}
            className={isFetching ? `${styles.toolbarFieldset} ${styles.toolbarDisabled}` : styles.toolbarFieldset}
          >
            {isFetching && <legend className="pf-v6-u-screen-reader">Filters — loading</legend>}
            {toolbar}
          </fieldset>
        </StackItem>
      )}
      {showBody ? (
        body
      ) : (
        <StackItem isFilled>
          <ListPanelStateContent
            isPending={isPending}
            error={error}
            onRetry={onRetry}
            errorTitle={errorTitle}
            isEmpty={isEmpty}
            hasActiveFilters={hasActiveFilters}
            onClearAllFilters={onClearAllFilters}
            noDataState={noDataState}
          />
        </StackItem>
      )}
    </>
  )

  if (tabKey && tabLabel && tabCtx) {
    const panelId = tabCtx.getPanelId(tabKey)

    return (
      // CSS `display: contents` makes this wrapper invisible to flex layout — inner StackItems remain
      // direct flex children of SynPanelContentStack despite the extra DOM node.
      <div id={panelId} role="tabpanel" aria-label={tabLabel} className={styles.tabPanelContents}>
        {content}
      </div>
    )
  }

  return content
}

export type NxListPanelToolbarProps = {
  /** Currently active filters — forwarded to `FilterBar`. */
  filters: FilterConfig[]
  /** Filter field definitions (shape, operators, labels). */
  filterDefinitions: FilterFieldDefinition[]
  /** Called when active filters change. */
  onFilterChange: (filters: FilterConfig[]) => void
  /** Called when "Clear all filters" is clicked. */
  clearAllFilters?: () => void
  /** Additional toolbar items after the filter inputs (e.g. refresh timestamp). */
  toolbarItemsAfterFilters?: ReactNode
  /** Compact mode — reduces toolbar padding. */
  isCompact?: boolean
  /** Actions slot rendered at the toolbar end (e.g. "Create" button). */
  actions?: ReactNode
}

/** Filter toolbar for use inside `NxListPanel`. */
export function NxListPanelToolbar({
  filters,
  filterDefinitions,
  onFilterChange,
  clearAllFilters,
  toolbarItemsAfterFilters,
  isCompact,
  actions,
}: NxListPanelToolbarProps) {
  return (
    <FilterBar
      className={styles.toolbar}
      fieldDefinitions={filterDefinitions}
      filters={filters}
      onFilterChange={onFilterChange}
      clearAllFilters={clearAllFilters}
      toolbarItemsAfterFilters={toolbarItemsAfterFilters}
      isCompact={isCompact}
      toolbarEnd={actions}
    />
  )
}

export type NxListPanelTableProps = {
  /** Table content (Thead, Tbody, etc.) */
  children: ReactNode
  /** Visually hidden accessible caption. */
  caption: string
  /** Pagination footer props. */
  footer?: TableFooterProps
  /** Table has expandable rows. */
  isExpandable?: boolean
  /** Opt out of fixed table layout (rarely needed). */
  useFixedLayout?: boolean
}

/** Paginated scrollable table for use inside `NxListPanel`. */
export function NxListPanelTable({ children, caption, footer, isExpandable, useFixedLayout }: NxListPanelTableProps) {
  return (
    <NxScrollableTableContainer
      caption={caption}
      footer={footer}
      isExpandable={isExpandable}
      useFixedLayout={useFixedLayout}
    >
      {children}
    </NxScrollableTableContainer>
  )
}

const MAX_SKELETON_ROWS = 20
const SKELETON_ROW_KEYS = Array.from({ length: MAX_SKELETON_ROWS }, (_, i) => `skeleton-row-${i}`)

export type NxListPanelSkeletonTbodyProps = {
  /** Number of columns — one `<Skeleton>` cell per column per row. Must match the visible `<Thead>`. */
  columnsCount: number
  /** Number of skeleton rows. Defaults to 5. */
  rowCount?: number
}

/** Skeleton tbody for use inside `NxListPanelTable` during a background refetch. Swap for real `<Tbody>` when `isFetching`. */
export function NxListPanelSkeletonTbody({ columnsCount, rowCount = 5 }: NxListPanelSkeletonTbodyProps) {
  return (
    <Tbody>
      {SKELETON_ROW_KEYS.slice(0, rowCount).map((key) => (
        <Tr key={key}>
          {Array.from({ length: columnsCount }, (_, i) => (
            <Td key={i}>
              <Skeleton />
            </Td>
          ))}
        </Tr>
      ))}
    </Tbody>
  )
}

export type NxListPanelTabsProps = Omit<TabsProps, 'activeKey' | 'onSelect' | 'ref'> & {
  /** Base URL path for tab routing. */
  basePath: string
  /** Tab key used when the URL has no tab segment. */
  defaultTab?: string
  /** Redirects to `defaultTab` when the URL tab is not in this list. */
  validTabs?: string[]
  /** `<Tab>` elements. */
  children: ReactNode
}

/** URL-driven tabs for use inside `NxListPanel`. */
export function NxListPanelTabs({ basePath, defaultTab, validTabs, children, ...tabsProps }: NxListPanelTabsProps) {
  const tabCtx = useNxListPanelTabContext()

  // Inject tabContentId into each Tab so PF's aria-controls targets the panel rendered by
  // the corresponding NxListPanelView (which provides the matching id via NxListPanelTabContext).
  // Cast via `unknown` because React.Children.map's inferred type is broader than ReactNode.
  const clonedChildren = (tabCtx
    ? React.Children.map(children, (child) => {
        if (!React.isValidElement(child)) return child
        const tab = child as React.ReactElement<{ eventKey: string | number; tabContentId?: string }>
        return React.cloneElement(tab, { tabContentId: tabCtx.getPanelId(String(tab.props.eventKey)) })
      })
    : children) as unknown as React.ReactNode

  return (
    <StackItem>
      <NxUrlTabs basePath={basePath} defaultTab={defaultTab} validTabs={validTabs} {...tabsProps}>
        {clonedChildren}
      </NxUrlTabs>
    </StackItem>
  )
}
