import { Button, Content } from '@patternfly/react-core'
import { RhUiAddIcon, RhUiImportIcon } from '@patternfly/react-icons'
import { ActionsColumn, Tbody, Td, Th, Thead, Tr } from '@patternfly/react-table'
import type { Decorator, Meta, StoryObj } from '@storybook/react-vite'

import { useTableSort } from '../../../hooks/useTableSort'
import { FilterOperatorEnum, FilterTypeEnum } from '../../../types/filters'
import { SynPage, SynPageBody } from '../../layout/SynPage'
import { SynPageHeader } from '../../layout/SynPageHeader'
import { SynEmptyStateNoData } from '../../states/SynEmptyStateNoData'

import {
  SynListPanel,
  SynListPanelSkeletonTbody,
  SynListPanelTable,
  SynListPanelToolbar,
  SynListPanelView,
} from './SynListPanel'
import { KitchenSinkListStory, ResourceActionsOverflowMenu, TabbedListStory } from './SynListPanel.stories.helpers'

const FILTER_DEFINITIONS = [
  {
    key: 'name',
    label: 'Name',
    type: FilterTypeEnum.TEXT,
    operators: [FilterOperatorEnum.CONTAINS],
    defaultOperator: FilterOperatorEnum.CONTAINS,
    placeholder: 'Filter by name',
  },
]

type SampleRow = { id: string; name: string; status: string }

const SAMPLE_ROWS: SampleRow[] = Array.from({ length: 8 }, (_, i) => ({
  id: String(i + 1),
  name: `resource-${String(i + 1).padStart(2, '0')}`,
  status: ['Active', 'Inactive', 'Pending'][i % 3],
}))

const ROW_ACTIONS = [
  { title: 'Edit resource', onClick: () => {} },
  { title: 'Delete resource', onClick: () => {} },
]

function SampleTable({ rows, isFetching }: Readonly<{ rows: SampleRow[]; isFetching?: boolean }>) {
  return (
    <SynListPanelTable caption="Sample resources">
      <Thead>
        <Tr>
          <Th>Name</Th>
          <Th>Status</Th>
          <Th screenReaderText="Actions" />
        </Tr>
      </Thead>
      {isFetching ? (
        <SynListPanelSkeletonTbody columnsCount={3} />
      ) : (
        <Tbody>
          {rows.map((row) => (
            <Tr key={row.id}>
              <Td dataLabel="Name">{row.name}</Td>
              <Td dataLabel="Status">{row.status}</Td>
              <Td isActionCell>
                <ActionsColumn items={ROW_ACTIONS} />
              </Td>
            </Tr>
          ))}
        </Tbody>
      )}
    </SynListPanelTable>
  )
}

const defaultToolbar = (
  <SynListPanelToolbar filters={[]} filterDefinitions={FILTER_DEFINITIONS} onFilterChange={() => {}} />
)

const PANEL_WRAPPER_STYLE = { height: '500px', display: 'flex', flexDirection: 'column' } as const
const PAGE_WRAPPER_STYLE = { height: '600px', display: 'flex', flexDirection: 'column' } as const

const panelDecorator: Decorator = (Story) => (
  <div style={PANEL_WRAPPER_STYLE}>
    <SynPage>
      <SynPageBody>
        <Story />
      </SynPageBody>
    </SynPage>
  </div>
)

const meta: Meta<typeof SynListPanel> = {
  component: SynListPanel,
  decorators: [panelDecorator],
  tags: ['autodocs'],
  parameters: {
    docs: {
      description: {
        component:
          'Compound component that composes `SynPanel`, toolbar, and table into a consistent list view.\n\n' +
          '**Sub-components:**\n' +
          '- `SynListPanel` — pure layout wrapper; always full-height and scrollable\n' +
          '- `SynListPanelView` — owns the state machine; toolbar is hidden during initial load\n' +
          '- `SynListPanelToolbar` — wraps `FilterBar` with an actions slot at the trailing end\n' +
          '- `SynListPanelTable` — scrollable, captioned table with optional pagination footer; swap in `SynListPanelSkeletonTbody` during background refetches\n' +
          '- `SynListPanelTabs` — URL-driven tabs for use inside `SynListPanel`\n\n' +
          '**State priority (inside `SynListPanelView`):** initial load → error (503 or standard) → filtered empty → no-data empty → data',
      },
    },
  },
}

export default meta

type Story = StoryObj<typeof meta>

/** Basic table with data — the default happy-path state. */
export const Default: Story = {
  render: () => (
    <SynListPanel>
      <SynListPanelView
        isPending={false}
        error={null}
        onRetry={() => {}}
        isEmpty={false}
        hasActiveFilters={false}
        onClearAllFilters={() => {}}
        toolbar={defaultToolbar}
        body={<SampleTable rows={SAMPLE_ROWS} />}
      />
    </SynListPanel>
  ),
}

/** `isPending={true}` — full-panel loading spinner; toolbar is hidden. */
export const Loading: Story = {
  render: () => (
    <SynListPanel>
      <SynListPanelView
        isPending
        error={null}
        onRetry={() => {}}
        isEmpty={false}
        hasActiveFilters={false}
        onClearAllFilters={() => {}}
        toolbar={defaultToolbar}
        body={<SampleTable rows={SAMPLE_ROWS} />}
      />
    </SynListPanel>
  ),
}

/** `error` set — shows an error state with a Retry button; toolbar is shown. */
export const Error: Story = {
  render: () => (
    <SynListPanel>
      <SynListPanelView
        isPending={false}
        error={{ status: 500, title: 'Internal Server Error', retryable: true }}
        onRetry={() => {}}
        isEmpty={false}
        hasActiveFilters={false}
        onClearAllFilters={() => {}}
        toolbar={defaultToolbar}
        body={<SampleTable rows={SAMPLE_ROWS} />}
      />
    </SynListPanel>
  ),
}

/** 503 error — auto-detected and shows the Service Unavailable state; toolbar is shown. */
export const ServiceUnavailable: Story = {
  render: () => (
    <SynListPanel>
      <SynListPanelView
        isPending={false}
        error={{ status: 503, title: 'Service Unavailable', retryable: true }}
        onRetry={() => {}}
        isEmpty={false}
        hasActiveFilters={false}
        onClearAllFilters={() => {}}
        toolbar={defaultToolbar}
        body={<SampleTable rows={SAMPLE_ROWS} />}
      />
    </SynListPanel>
  ),
}

/** `errorTitle` override — replaces the default "Error" heading with a page-specific label. */
export const ErrorWithCustomTitle: Story = {
  render: () => (
    <SynListPanel>
      <SynListPanelView
        isPending={false}
        error="Network error"
        errorTitle="Error loading identity providers"
        onRetry={() => {}}
        isEmpty={false}
        hasActiveFilters={false}
        onClearAllFilters={() => {}}
        toolbar={defaultToolbar}
        body={<SampleTable rows={SAMPLE_ROWS} />}
      />
    </SynListPanel>
  ),
}

/** Toggle `isFetching` in the Controls panel to show/hide skeleton rows during a background refetch. */
export const SkeletonFetching: StoryObj<{ isFetching: boolean }> = {
  args: { isFetching: true },
  argTypes: {
    isFetching: { control: 'boolean', description: 'Simulates a background refetch — shows skeleton rows.' },
  },
  render: ({ isFetching }) => (
    <SynListPanel>
      <SynListPanelView
        isPending={false}
        isFetching={isFetching}
        error={null}
        onRetry={() => {}}
        isEmpty={false}
        hasActiveFilters={false}
        onClearAllFilters={() => {}}
        toolbar={<SynListPanelToolbar filters={[]} filterDefinitions={FILTER_DEFINITIONS} onFilterChange={() => {}} />}
        body={<SampleTable rows={SAMPLE_ROWS} isFetching={isFetching} />}
      />
    </SynListPanel>
  ),
}

/** `isEmpty && hasActiveFilters` — filter empty state with "Clear all filters" action; toolbar shown. */
export const FilteredEmpty: Story = {
  render: () => (
    <SynListPanel>
      <SynListPanelView
        isPending={false}
        error={null}
        onRetry={() => {}}
        isEmpty
        hasActiveFilters
        onClearAllFilters={() => {}}
        toolbar={defaultToolbar}
        body={<SampleTable rows={[]} />}
      />
    </SynListPanel>
  ),
}

/** `isEmpty` with no active filters — default no-data empty state; toolbar shown. */
export const NoData: Story = {
  render: () => (
    <SynListPanel>
      <SynListPanelView
        isPending={false}
        error={null}
        onRetry={() => {}}
        isEmpty
        hasActiveFilters={false}
        onClearAllFilters={() => {}}
        toolbar={defaultToolbar}
        body={<SampleTable rows={[]} />}
      />
    </SynListPanel>
  ),
}

/**
 * `isEmpty` with no toolbar — omit the `toolbar` prop to suppress the filter bar entirely.
 * Use this when the empty state should be a full-panel call-to-action (e.g. a "Get started" splash)
 * rather than an empty search bar alongside the default empty state.
 */
export const NoDataNoToolbar: Story = {
  render: () => (
    <SynListPanel>
      <SynListPanelView
        isPending={false}
        error={null}
        onRetry={() => {}}
        isEmpty
        hasActiveFilters={false}
        onClearAllFilters={() => {}}
        noDataState={
          <SynEmptyStateNoData
            title="No resources yet"
            description="Create your first resource to get started."
            buttonText="Create resource"
            addData={() => {}}
          />
        }
        body={<SampleTable rows={[]} />}
      />
    </SynListPanel>
  ),
}

/** Custom `noDataState` — pass your own empty state component. */
export const NoDataCustom: Story = {
  render: () => (
    <SynListPanel>
      <SynListPanelView
        isPending={false}
        error={null}
        onRetry={() => {}}
        isEmpty
        hasActiveFilters={false}
        onClearAllFilters={() => {}}
        noDataState={
          <SynEmptyStateNoData
            title="No resources yet"
            description="Create your first resource to get started."
            buttonText="Create resource"
            addData={() => {}}
          />
        }
        toolbar={defaultToolbar}
        body={<SampleTable rows={[]} />}
      />
    </SynListPanel>
  ),
}

/** Toolbar with a single action button in the `actions` slot. */
export const WithActions: Story = {
  render: () => (
    <SynListPanel>
      <SynListPanelView
        isPending={false}
        error={null}
        onRetry={() => {}}
        isEmpty={false}
        hasActiveFilters={false}
        onClearAllFilters={() => {}}
        toolbar={
          <SynListPanelToolbar
            filters={[]}
            filterDefinitions={FILTER_DEFINITIONS}
            onFilterChange={() => {}}
            actions={
              <Button variant="primary" icon={<RhUiAddIcon />}>
                Create resource
              </Button>
            }
          />
        }
        body={<SampleTable rows={SAMPLE_ROWS} />}
      />
    </SynListPanel>
  ),
}

/** Multiple buttons in the actions slot — primary before secondary per AO design system §8. */
export const WithMultipleButtons: Story = {
  render: () => (
    <SynListPanel>
      <SynListPanelView
        isPending={false}
        error={null}
        onRetry={() => {}}
        isEmpty={false}
        hasActiveFilters={false}
        onClearAllFilters={() => {}}
        toolbar={
          <SynListPanelToolbar
            filters={[]}
            filterDefinitions={FILTER_DEFINITIONS}
            onFilterChange={() => {}}
            actions={
              <>
                <Button variant="primary" icon={<RhUiAddIcon />}>
                  Create resource
                </Button>
                <Button variant="secondary" icon={<RhUiImportIcon />}>
                  Import resource
                </Button>
              </>
            }
          />
        }
        body={<SampleTable rows={SAMPLE_ROWS} />}
      />
    </SynListPanel>
  ),
}

/** Primary button with a kebab overflow menu for secondary actions — use when toolbar has more than two actions. */
export const WithActionOverflowMenu: Story = {
  render: () => (
    <SynListPanel>
      <SynListPanelView
        isPending={false}
        error={null}
        onRetry={() => {}}
        isEmpty={false}
        hasActiveFilters={false}
        onClearAllFilters={() => {}}
        toolbar={
          <SynListPanelToolbar
            filters={[]}
            filterDefinitions={FILTER_DEFINITIONS}
            onFilterChange={() => {}}
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
        body={<SampleTable rows={SAMPLE_ROWS} />}
      />
    </SynListPanel>
  ),
}

/** Arbitrary content between the toolbar and table — e.g. a descriptive paragraph. */
export const WithContentBetween: Story = {
  render: () => (
    <SynListPanel>
      <SynListPanelView
        isPending={false}
        error={null}
        onRetry={() => {}}
        isEmpty={false}
        hasActiveFilters={false}
        onClearAllFilters={() => {}}
        toolbar={defaultToolbar}
        body={
          <>
            <Content>Resources define the set of actions users can perform in this context.</Content>
            <SampleTable rows={SAMPLE_ROWS} />
          </>
        }
      />
    </SynListPanel>
  ),
}

/** Two tabs each with their own `SynListPanelView`; active tab driven by URL. Click tabs to switch content. */
export const TabbedList: Story = {
  render: () => <TabbedListStory />,
}

/** Read-only list — filters + table, no create action. Mirrors the Executions page pattern. */
export const ReadOnlyList: Story = {
  render: function ReadOnlyListStory() {
    return (
      <div style={PAGE_WRAPPER_STYLE}>
        <SynPage>
          <SynPageHeader title="Executions" />
          <SynPageBody>
            <SynListPanel>
              <SynListPanelView
                isPending={false}
                error={null}
                onRetry={() => {}}
                isEmpty={false}
                hasActiveFilters={false}
                onClearAllFilters={() => {}}
                toolbar={defaultToolbar}
                body={<SampleTable rows={SAMPLE_ROWS} />}
              />
            </SynListPanel>
          </SynPageBody>
        </SynPage>
      </div>
    )
  },
}

/** Click the Name or Status column headers to toggle ascending/descending sort order. Client-side via `useTableSort`. */
export const WithSorting: Story = {
  render: function WithSortingStory() {
    const { activeSortIndex, getSortParams, sortData } = useTableSort({ initialSortIndex: 0 })
    const sortedRows = sortData(SAMPLE_ROWS, (row) => {
      if (activeSortIndex === 1) return row.status
      return row.name
    })
    return (
      <SynListPanel>
        <SynListPanelView
          isPending={false}
          error={null}
          onRetry={() => {}}
          isEmpty={false}
          hasActiveFilters={false}
          onClearAllFilters={() => {}}
          toolbar={defaultToolbar}
          body={
            <SynListPanelTable caption="Sample resources">
              <Thead>
                <Tr>
                  <Th sort={getSortParams(0)}>Name</Th>
                  <Th sort={getSortParams(1)}>Status</Th>
                  <Th screenReaderText="Actions" />
                </Tr>
              </Thead>
              <Tbody>
                {sortedRows.map((row) => (
                  <Tr key={row.id}>
                    <Td dataLabel="Name">{row.name}</Td>
                    <Td dataLabel="Status">{row.status}</Td>
                    <Td isActionCell>
                      <ActionsColumn items={ROW_ACTIONS} />
                    </Td>
                  </Tr>
                ))}
              </Tbody>
            </SynListPanelTable>
          }
        />
      </SynListPanel>
    )
  },
}

/**
 * Every feature active at once: multi-field filtering (name text + status select), client-side
 * sorting on all three columns, a descriptive paragraph between the toolbar and table, multiple
 * toolbar action buttons, skeleton background-fetch (click the refresh icon), and a pagination footer.
 */
export const KitchenSink: Story = {
  render: () => <KitchenSinkListStory />,
}
