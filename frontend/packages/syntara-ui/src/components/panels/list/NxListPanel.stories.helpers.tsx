/**
 * Story-only helpers for NxListPanel.stories.tsx.
 * Extracted to keep the stories file within the max-lines limit.
 * Not part of the public component API.
 */
import { Badge, Button, Content, Tab, TabTitleText } from '@patternfly/react-core'
import { RhUiAddIcon, RhUiExportIcon, RhUiImportIcon, RhUiRefreshIcon } from '@patternfly/react-icons'
import { ActionsColumn, Tbody, Td, Th, Thead, Tr } from '@patternfly/react-table'
import { useMemo, useState } from 'react'

import { useTableSort } from '../../../hooks/useTableSort'
import { useUrlTab } from '../../../hooks/useUrlTab'
import { createTestRouter } from '../../../test/createTestRouter'
import {
  type FilterConfig,
  type FilterFieldDefinition,
  FilterOperatorEnum,
  FilterTypeEnum,
} from '../../../types/filters'
import { IconLabel } from '../../IconLabel'
import { SynKebabMenu } from '../../SynKebabMenu'

import {
  NxListPanel,
  NxListPanelSkeletonTbody,
  NxListPanelTable,
  NxListPanelTabs,
  NxListPanelToolbar,
  NxListPanelView,
} from './NxListPanel'

/** Overflow kebab with Import / Export actions; for use in WithActionOverflowMenu story. */
export function ResourceActionsOverflowMenu() {
  return (
    <SynKebabMenu
      aria-label="More resource actions"
      actions={[
        { key: 'import', title: <IconLabel icon={<RhUiImportIcon />}>Import resource</IconLabel>, onClick: () => {} },
        { key: 'export', title: <IconLabel icon={<RhUiExportIcon />}>Export resource</IconLabel>, onClick: () => {} },
      ]}
    />
  )
}

const TABBED_FILTER_DEFINITIONS = [
  {
    key: 'name',
    label: 'Name',
    type: FilterTypeEnum.TEXT,
    operators: [FilterOperatorEnum.CONTAINS],
    defaultOperator: FilterOperatorEnum.CONTAINS,
    placeholder: 'Filter by name',
  },
]

type TabbedRow = { id: string; name: string; status: string }

const TABBED_BASE_PATH = '/group/resources'

const MEMBERS: TabbedRow[] = Array.from({ length: 4 }, (_, i) => ({
  id: `m${i}`,
  name: `member-${String(i + 1).padStart(2, '0')}`,
  status: 'Active',
}))

const ROLES: TabbedRow[] = Array.from({ length: 3 }, (_, i) => ({
  id: `r${i}`,
  name: `role-${String(i + 1).padStart(2, '0')}`,
  status: 'Active',
}))

function TabbedListContent() {
  const [activeTab] = useUrlTab(TABBED_BASE_PATH, 'members')

  return (
    <NxListPanel>
      <NxListPanelTabs basePath={TABBED_BASE_PATH} defaultTab="members" aria-label="Group resources">
        <Tab
          eventKey="members"
          title={
            <TabTitleText>
              Members <Badge isRead>{MEMBERS.length}</Badge>
            </TabTitleText>
          }
        />
        <Tab
          eventKey="roles"
          title={
            <TabTitleText>
              Assignments <Badge isRead>{ROLES.length}</Badge>
            </TabTitleText>
          }
        />
      </NxListPanelTabs>

      {activeTab === 'members' && (
        <NxListPanelView
          isPending={false}
          error={null}
          onRetry={() => {}}
          isEmpty={MEMBERS.length === 0}
          hasActiveFilters={false}
          onClearAllFilters={() => {}}
          tabKey="members"
          tabLabel="Members"
          toolbar={
            <NxListPanelToolbar filters={[]} filterDefinitions={TABBED_FILTER_DEFINITIONS} onFilterChange={() => {}} />
          }
          body={
            <NxListPanelTable caption="Members">
              <Thead>
                <Tr>
                  <Th>Name</Th>
                  <Th>Status</Th>
                </Tr>
              </Thead>
              <Tbody>
                {MEMBERS.map((row) => (
                  <Tr key={row.id}>
                    <Td dataLabel="Name">{row.name}</Td>
                    <Td dataLabel="Status">{row.status}</Td>
                  </Tr>
                ))}
              </Tbody>
            </NxListPanelTable>
          }
        />
      )}

      {activeTab === 'roles' && (
        <NxListPanelView
          isPending={false}
          error={null}
          onRetry={() => {}}
          isEmpty={ROLES.length === 0}
          hasActiveFilters={false}
          onClearAllFilters={() => {}}
          tabKey="roles"
          tabLabel="Assignments"
          toolbar={
            <NxListPanelToolbar filters={[]} filterDefinitions={TABBED_FILTER_DEFINITIONS} onFilterChange={() => {}} />
          }
          body={
            <NxListPanelTable caption="Role assignments">
              <Thead>
                <Tr>
                  <Th>Name</Th>
                  <Th>Status</Th>
                </Tr>
              </Thead>
              <Tbody>
                {ROLES.map((row) => (
                  <Tr key={row.id}>
                    <Td dataLabel="Name">{row.name}</Td>
                    <Td dataLabel="Status">{row.status}</Td>
                  </Tr>
                ))}
              </Tbody>
            </NxListPanelTable>
          }
        />
      )}
    </NxListPanel>
  )
}

const TabbedListWrapper = createTestRouter(`${TABBED_BASE_PATH}/members`)

/** Renders the tabbed list inside a memory router; for use as a story render function. */
export function TabbedListStory() {
  return (
    <TabbedListWrapper>
      <TabbedListContent />
    </TabbedListWrapper>
  )
}

type KitchenRow = { id: string; name: string; status: string; count: number }

const KITCHEN_ROWS: KitchenRow[] = Array.from({ length: 14 }, (_, i) => ({
  id: String(i + 1),
  name: `resource-${String(i + 1).padStart(2, '0')}`,
  status: (['Active', 'Inactive', 'Pending'] as const)[i % 3],
  count: (i + 1) * 5,
}))

const KITCHEN_FILTER_DEFINITIONS: FilterFieldDefinition[] = [
  {
    key: 'name',
    label: 'Name',
    type: FilterTypeEnum.TEXT,
    operators: [FilterOperatorEnum.CONTAINS],
    defaultOperator: FilterOperatorEnum.CONTAINS,
    placeholder: 'Filter by name',
  },
  {
    key: 'status',
    label: 'Status',
    type: FilterTypeEnum.SELECT,
    operators: [FilterOperatorEnum.EQ],
    defaultOperator: FilterOperatorEnum.EQ,
    options: [
      { label: 'Active', value: 'Active' },
      { label: 'Inactive', value: 'Inactive' },
      { label: 'Pending', value: 'Pending' },
    ],
    searchable: false,
  },
]

const KITCHEN_ROW_ACTIONS = [
  { title: 'Edit resource', onClick: () => {} },
  { title: 'Delete resource', onClick: () => {}, isDanger: true },
]

/**
 * Full kitchen-sink story component: filtering, sorting, description content between toolbar and
 * table, multiple action buttons, skeleton background-fetch, and a pagination footer.
 */
export function KitchenSinkListStory() {
  const [filters, setFilters] = useState<FilterConfig[]>([])
  const [isFetching, setIsFetching] = useState(false)
  const { activeSortIndex, getSortParams, sortData } = useTableSort({ initialSortIndex: 0 })

  function handleSimulateRefresh() {
    setIsFetching(true)
    setTimeout(() => {
      setIsFetching(false)
    }, 1500)
  }

  const hasActiveFilters = filters.length > 0

  const filteredRows = useMemo<KitchenRow[]>(
    () =>
      KITCHEN_ROWS.filter((row) => {
        for (const filter of filters) {
          if (filter.key === 'name' && typeof filter.value === 'string') {
            if (!row.name.toLowerCase().includes(filter.value.toLowerCase())) return false
          }
          if (filter.key === 'status' && typeof filter.value === 'string') {
            if (row.status !== filter.value) return false
          }
        }
        return true
      }),
    [filters]
  )

  const sortedRows = sortData(filteredRows, (row) => {
    if (activeSortIndex === 1) return row.status
    if (activeSortIndex === 2) return row.count
    return row.name
  })

  function clearFilters() {
    setFilters([])
  }

  return (
    <NxListPanel>
      <NxListPanelView
        isPending={false}
        isFetching={isFetching}
        error={null}
        onRetry={() => {}}
        isEmpty={sortedRows.length === 0}
        hasActiveFilters={hasActiveFilters}
        onClearAllFilters={clearFilters}
        toolbar={
          <NxListPanelToolbar
            filters={filters}
            filterDefinitions={KITCHEN_FILTER_DEFINITIONS}
            onFilterChange={setFilters}
            clearAllFilters={clearFilters}
            toolbarItemsAfterFilters={
              <Button
                variant="plain"
                aria-label="Simulate background fetch"
                icon={<RhUiRefreshIcon />}
                onClick={handleSimulateRefresh}
                isDisabled={isFetching}
              />
            }
            actions={
              <>
                <ResourceActionsOverflowMenu />
                <Button variant="primary" icon={<RhUiAddIcon />}>
                  Create resource
                </Button>
              </>
            }
          />
        }
        body={
          <>
            <Content>
              Manage your resources below. Use the Name and Status filters to narrow results, click column headers to
              sort, and use the refresh icon or action menu to manage resources.
            </Content>
            <NxListPanelTable
              caption="Resources"
              footer={{
                page: 1,
                perPage: 20,
                total: KITCHEN_ROWS.length,
                hasNext: false,
                onPrev: () => {},
                onNext: () => {},
                onPerPageChange: () => {},
              }}
            >
              <Thead>
                <Tr>
                  <Th sort={getSortParams(0)}>Name</Th>
                  <Th sort={getSortParams(1)}>Status</Th>
                  <Th sort={getSortParams(2)}>Count</Th>
                  <Th screenReaderText="Actions" />
                </Tr>
              </Thead>
              {isFetching ? (
                <NxListPanelSkeletonTbody columnsCount={4} />
              ) : (
                <Tbody>
                  {sortedRows.map((row) => (
                    <Tr key={row.id}>
                      <Td dataLabel="Name">{row.name}</Td>
                      <Td dataLabel="Status">{row.status}</Td>
                      <Td dataLabel="Count">{row.count}</Td>
                      <Td isActionCell>
                        <ActionsColumn items={KITCHEN_ROW_ACTIONS} />
                      </Td>
                    </Tr>
                  ))}
                </Tbody>
              )}
            </NxListPanelTable>
          </>
        }
      />
    </NxListPanel>
  )
}
