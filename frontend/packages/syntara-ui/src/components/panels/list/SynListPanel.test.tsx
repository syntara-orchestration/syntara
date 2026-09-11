import { Tab } from '@patternfly/react-core'
import { Tbody, Td, Th, Thead, Tr } from '@patternfly/react-table'
import { act, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactElement } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

vi.mock('@tanstack/react-router', async () => vi.importActual('@tanstack/react-router'))

import { createTestRouter } from '../../../test/createTestRouter'
import { FilterOperatorEnum, FilterTypeEnum } from '../../../types/filters'

import {
  SynListPanel,
  SynListPanelSkeletonTbody,
  SynListPanelTable,
  SynListPanelTabs,
  SynListPanelToolbar,
  SynListPanelView,
} from './SynListPanel'

const FILTER_DEFINITIONS = [
  {
    key: 'name',
    label: 'Name',
    type: FilterTypeEnum.TEXT,
    operators: [FilterOperatorEnum.CONTAINS],
    defaultOperator: FilterOperatorEnum.CONTAINS,
  },
]

const NOOP = () => {}

const minimalToolbar = <SynListPanelToolbar filters={[]} filterDefinitions={FILTER_DEFINITIONS} onFilterChange={NOOP} />

const minimalTable = (
  <SynListPanelTable caption="Test table">
    <Thead>
      <Tr>
        <Th>Name</Th>
      </Tr>
    </Thead>
    <Tbody>
      <Tr>
        <Td>Row 1</Td>
      </Tr>
    </Tbody>
  </SynListPanelTable>
)

function baseViewProps() {
  return {
    isPending: false,
    error: null,
    onRetry: NOOP,
    isEmpty: false,
    hasActiveFilters: false,
    onClearAllFilters: NOOP,
  }
}

const PANEL_WRAPPER_STYLE = { height: '600px', display: 'flex', flexDirection: 'column' } as const

function renderPanel(ui: ReactElement) {
  return render(<div style={PANEL_WRAPPER_STYLE}>{ui}</div>)
}

// Router wrapper for tab tests
function withRouter(ui: ReactElement, path = '/group/tabs') {
  const Wrapper = createTestRouter(path)
  return renderPanel(<Wrapper>{ui}</Wrapper>)
}

describe('SynListPanel', () => {
  it('renders toolbar and table in the data state', () => {
    renderPanel(
      <SynListPanel>
        <SynListPanelView {...baseViewProps()} toolbar={minimalToolbar} body={minimalTable} />
      </SynListPanel>
    )
    expect(screen.getByRole('search', { name: 'Filters' })).toBeInTheDocument()
    expect(screen.getByRole('grid')).toBeInTheDocument()
  })
})

describe('SynListPanelView', () => {
  describe('data state', () => {
    it('renders toolbar and table when data is available', () => {
      renderPanel(
        <SynListPanel>
          <SynListPanelView {...baseViewProps()} toolbar={minimalToolbar} body={minimalTable} />
        </SynListPanel>
      )

      expect(screen.getByRole('search', { name: 'Filters' })).toBeInTheDocument()
      expect(screen.getByRole('grid')).toBeInTheDocument()
    })

    it('has no accessibility violations in the data state', async () => {
      const { container } = renderPanel(
        <SynListPanel>
          <SynListPanelView {...baseViewProps()} toolbar={minimalToolbar} body={minimalTable} />
        </SynListPanel>
      )

      expect(await axe(container)).toHaveNoViolations()
    })
  })

  describe('loading state (isPending)', () => {
    it('shows loading spinner and hides both the table and toolbar', () => {
      renderPanel(
        <SynListPanel>
          <SynListPanelView {...baseViewProps()} isPending toolbar={minimalToolbar} body={minimalTable} />
        </SynListPanel>
      )

      expect(screen.getByTestId('loading-state')).toBeInTheDocument()
      expect(screen.queryByRole('grid')).not.toBeInTheDocument()
      expect(screen.queryByRole('search', { name: 'Filters' })).not.toBeInTheDocument()
    })

    it('has no accessibility violations in the loading state', async () => {
      const { container } = renderPanel(
        <SynListPanel>
          <SynListPanelView {...baseViewProps()} isPending toolbar={minimalToolbar} body={minimalTable} />
        </SynListPanel>
      )

      expect(await axe(container)).toHaveNoViolations()
    })
  })

  describe('error state', () => {
    it('shows error state with retry button for retryable errors, hides table, shows toolbar', async () => {
      const user = userEvent.setup()
      const onRetry = vi.fn()
      const error = { status: 500, title: 'Internal Server Error', retryable: true }

      renderPanel(
        <SynListPanel>
          <SynListPanelView
            {...baseViewProps()}
            error={error}
            onRetry={onRetry}
            toolbar={minimalToolbar}
            body={minimalTable}
          />
        </SynListPanel>
      )

      expect(screen.getByTestId('error-state')).toBeInTheDocument()
      expect(screen.queryByRole('grid')).not.toBeInTheDocument()
      expect(screen.getByRole('search', { name: 'Filters' })).toBeInTheDocument()

      await user.click(screen.getByRole('button', { name: 'Retry' }))
      expect(onRetry).toHaveBeenCalledOnce()
    })

    it('has no accessibility violations in the error state', async () => {
      const error = { status: 500, title: 'Internal Server Error', retryable: true }
      const { container } = renderPanel(
        <SynListPanel>
          <SynListPanelView {...baseViewProps()} error={error} toolbar={minimalToolbar} body={minimalTable} />
        </SynListPanel>
      )

      expect(await axe(container)).toHaveNoViolations()
    })
  })

  describe('service unavailable state', () => {
    it('shows service unavailable state for 503 errors, hides table, shows toolbar', () => {
      const error = { status: 503, title: 'Service Unavailable', retryable: true }

      renderPanel(
        <SynListPanel>
          <SynListPanelView {...baseViewProps()} error={error} toolbar={minimalToolbar} body={minimalTable} />
        </SynListPanel>
      )

      expect(screen.getByText('Service Unavailable')).toBeInTheDocument()
      expect(screen.queryByRole('grid')).not.toBeInTheDocument()
      expect(screen.getByRole('search', { name: 'Filters' })).toBeInTheDocument()
    })
  })

  describe('filtered empty state', () => {
    it('shows filter empty state and toolbar when filters are active', () => {
      renderPanel(
        <SynListPanel>
          <SynListPanelView
            {...baseViewProps()}
            isEmpty
            hasActiveFilters
            toolbar={minimalToolbar}
            body={minimalTable}
          />
        </SynListPanel>
      )

      expect(screen.getByText('No results found')).toBeInTheDocument()
      expect(screen.getByRole('search', { name: 'Filters' })).toBeInTheDocument()
      expect(screen.queryByRole('grid')).not.toBeInTheDocument()
    })

    it('calls onClearAllFilters when "Clear all filters" is clicked', async () => {
      const user = userEvent.setup()
      const onClearAllFilters = vi.fn()

      renderPanel(
        <SynListPanel>
          <SynListPanelView
            {...baseViewProps()}
            isEmpty
            hasActiveFilters
            onClearAllFilters={onClearAllFilters}
            toolbar={minimalToolbar}
            body={minimalTable}
          />
        </SynListPanel>
      )

      await user.click(screen.getByRole('button', { name: 'Clear all filters' }))
      expect(onClearAllFilters).toHaveBeenCalledOnce()
    })

    it('has no accessibility violations in the filtered empty state', async () => {
      const { container } = renderPanel(
        <SynListPanel>
          <SynListPanelView
            {...baseViewProps()}
            isEmpty
            hasActiveFilters
            toolbar={minimalToolbar}
            body={minimalTable}
          />
        </SynListPanel>
      )

      expect(await axe(container)).toHaveNoViolations()
    })
  })

  describe('no-data empty state', () => {
    it('shows default no-data empty state when isEmpty and no active filters, shows toolbar', () => {
      renderPanel(
        <SynListPanel>
          <SynListPanelView {...baseViewProps()} isEmpty toolbar={minimalToolbar} body={minimalTable} />
        </SynListPanel>
      )

      expect(screen.getByText('No data available')).toBeInTheDocument()
      expect(screen.queryByRole('grid')).not.toBeInTheDocument()
      expect(screen.getByRole('search', { name: 'Filters' })).toBeInTheDocument()
    })

    it('renders custom noDataState when provided', () => {
      renderPanel(
        <SynListPanel>
          <SynListPanelView
            {...baseViewProps()}
            isEmpty
            noDataState={<div>Custom empty state</div>}
            toolbar={minimalToolbar}
            body={minimalTable}
          />
        </SynListPanel>
      )

      expect(screen.getByText('Custom empty state')).toBeInTheDocument()
    })

    it('has no accessibility violations in the no-data empty state', async () => {
      const { container } = renderPanel(
        <SynListPanel>
          <SynListPanelView {...baseViewProps()} isEmpty toolbar={minimalToolbar} body={minimalTable} />
        </SynListPanel>
      )

      expect(await axe(container)).toHaveNoViolations()
    })
  })

  describe('toolbar slot', () => {
    it('renders toolbar in the data state', () => {
      renderPanel(
        <SynListPanel>
          <SynListPanelView {...baseViewProps()} toolbar={minimalToolbar} body={minimalTable} />
        </SynListPanel>
      )

      expect(screen.getByRole('search', { name: 'Filters' })).toBeInTheDocument()
    })

    it('hides toolbar when no toolbar prop is provided', () => {
      renderPanel(
        <SynListPanel>
          <SynListPanelView {...baseViewProps()} body={minimalTable} />
        </SynListPanel>
      )

      expect(screen.queryByRole('search', { name: 'Filters' })).not.toBeInTheDocument()
    })

    it('shows actions rendered inside toolbar', () => {
      renderPanel(
        <SynListPanel>
          <SynListPanelView
            {...baseViewProps()}
            toolbar={
              <SynListPanelToolbar
                filters={[]}
                filterDefinitions={FILTER_DEFINITIONS}
                onFilterChange={NOOP}
                actions={<button>Create item</button>}
              />
            }
            body={minimalTable}
          />
        </SynListPanel>
      )

      expect(screen.getByRole('button', { name: 'Create item' })).toBeInTheDocument()
    })
  })

  describe('isFetching state (background refetch)', () => {
    it('still renders body and toolbar when isFetching', () => {
      renderPanel(
        <SynListPanel>
          <SynListPanelView {...baseViewProps()} isFetching toolbar={minimalToolbar} body={minimalTable} />
        </SynListPanel>
      )

      expect(screen.getByRole('grid')).toBeInTheDocument()
      expect(screen.getByRole('search', { name: 'Filters' })).toBeInTheDocument()
    })

    it('wraps toolbar in a disabled fieldset when isFetching', () => {
      renderPanel(
        <SynListPanel>
          <SynListPanelView {...baseViewProps()} isFetching toolbar={minimalToolbar} body={minimalTable} />
        </SynListPanel>
      )

      expect(screen.getByRole('group', { name: 'Filters — loading' })).toBeDisabled()
    })

    it('has no accessibility violations when isFetching', async () => {
      const { container } = renderPanel(
        <SynListPanel>
          <SynListPanelView {...baseViewProps()} isFetching toolbar={minimalToolbar} body={minimalTable} />
        </SynListPanel>
      )

      expect(await axe(container)).toHaveNoViolations()
    })
  })

  describe('body prop', () => {
    it('renders body content in the data state', () => {
      renderPanel(
        <SynListPanel>
          <SynListPanelView
            {...baseViewProps()}
            toolbar={minimalToolbar}
            body={
              <>
                <p>Descriptive text</p>
                {minimalTable}
              </>
            }
          />
        </SynListPanel>
      )

      expect(screen.getByText('Descriptive text')).toBeInTheDocument()
    })

    it('hides body during empty state', () => {
      renderPanel(
        <SynListPanel>
          <SynListPanelView
            {...baseViewProps()}
            isEmpty
            toolbar={minimalToolbar}
            body={
              <>
                <p>Descriptive text</p>
                {minimalTable}
              </>
            }
          />
        </SynListPanel>
      )

      expect(screen.queryByText('Descriptive text')).not.toBeInTheDocument()
    })
  })
})

describe('SynListPanelTable', () => {
  it('renders the table caption accessibly', () => {
    renderPanel(
      <SynListPanel>
        <SynListPanelView
          {...baseViewProps()}
          body={
            <SynListPanelTable caption="My resources">
              <Thead>
                <Tr>
                  <Th>Name</Th>
                </Tr>
              </Thead>
              <Tbody>
                <Tr>
                  <Td>Item 1</Td>
                </Tr>
              </Tbody>
            </SynListPanelTable>
          }
        />
      </SynListPanel>
    )

    expect(screen.getByRole('grid', { name: 'My resources' })).toBeInTheDocument()
  })

  it('renders pagination footer when footer props are provided', () => {
    renderPanel(
      <SynListPanel>
        <SynListPanelView
          {...baseViewProps()}
          body={
            <SynListPanelTable
              caption="Test table"
              footer={{ page: 1, perPage: 20, hasNext: false, onPrev: NOOP, onNext: NOOP, onPerPageChange: NOOP }}
            >
              <Thead>
                <Tr>
                  <Th>Name</Th>
                </Tr>
              </Thead>
              <Tbody>
                <Tr>
                  <Td>Row 1</Td>
                </Tr>
              </Tbody>
            </SynListPanelTable>
          }
        />
      </SynListPanel>
    )

    expect(screen.getByRole('navigation', { name: 'Pagination' })).toBeInTheDocument()
  })
})

describe('SynListPanelSkeletonTbody', () => {
  function renderSkeletonTbody(columnsCount: number, rowCount?: number) {
    return render(
      <table>
        <SynListPanelSkeletonTbody columnsCount={columnsCount} rowCount={rowCount} />
      </table>
    )
  }

  it('renders the correct number of rows', () => {
    renderSkeletonTbody(3, 4)
    expect(screen.getAllByRole('row')).toHaveLength(4)
  })

  it('renders the correct number of cells per row', () => {
    renderSkeletonTbody(3, 2)
    for (const row of screen.getAllByRole('row')) {
      expect(within(row).getAllByRole('cell')).toHaveLength(3)
    }
  })

  it('defaults to 5 rows when rowCount is not provided', () => {
    renderSkeletonTbody(2)
    expect(screen.getAllByRole('row')).toHaveLength(5)
  })

  it('has no accessibility violations', async () => {
    const { container } = renderSkeletonTbody(3, 5)
    expect(await axe(container)).toHaveNoViolations()
  })
})

describe('SynListPanelTabs', () => {
  it('renders tab bar with the correct tabs', async () => {
    withRouter(
      <SynListPanel>
        <SynListPanelTabs basePath="/group/tabs" defaultTab="members" aria-label="Group tabs">
          <Tab eventKey="members" title="Members" />
          <Tab eventKey="roles" title="Roles" />
        </SynListPanelTabs>
      </SynListPanel>,
      '/group/tabs/members'
    )

    expect(await screen.findByRole('tab', { name: 'Members' })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'Roles' })).toBeInTheDocument()
  })

  it('activates the tab that matches the URL', async () => {
    withRouter(
      <SynListPanel>
        <SynListPanelTabs basePath="/group/tabs" defaultTab="members" aria-label="Group tabs">
          <Tab eventKey="members" title="Members" />
          <Tab eventKey="roles" title="Roles" />
        </SynListPanelTabs>
      </SynListPanel>,
      '/group/tabs/roles'
    )

    expect(await screen.findByRole('tab', { name: 'Roles', selected: true })).toBeInTheDocument()
  })

  it('tab aria-controls targets the matching tabpanel id', async () => {
    withRouter(
      <SynListPanel>
        <SynListPanelTabs basePath="/group/tabs" defaultTab="members" aria-label="Group tabs">
          <Tab eventKey="members" title="Members" />
          <Tab eventKey="roles" title="Roles" />
        </SynListPanelTabs>
        <SynListPanelView
          {...baseViewProps()}
          tabKey="members"
          tabLabel="Members"
          toolbar={minimalToolbar}
          body={minimalTable}
        />
      </SynListPanel>,
      '/group/tabs/members'
    )

    const tab = await screen.findByRole('tab', { name: 'Members' })
    const tabPanel = screen.getByRole('tabpanel', { name: 'Members' })
    expect(tab.getAttribute('aria-controls')).toBe(tabPanel.id)
  })

  it('has no accessibility violations', async () => {
    const { container } = withRouter(
      <SynListPanel>
        <SynListPanelTabs basePath="/group/tabs" defaultTab="members" aria-label="Group tabs">
          <Tab eventKey="members" title="Members" />
          <Tab eventKey="roles" title="Roles" />
        </SynListPanelTabs>
        <SynListPanelView
          {...baseViewProps()}
          tabKey="members"
          tabLabel="Members"
          toolbar={minimalToolbar}
          body={minimalTable}
        />
      </SynListPanel>,
      '/group/tabs/members'
    )

    await screen.findByRole('tab', { name: 'Members' })
    // `findByRole` resolves as soon as the tab paints, but RouterProvider is still settling:
    // TanStack Router's internal `OnRendered` re-renders when the `resolvedLocation` store
    // updates a microtask later. `axe()` takes long enough that the update would otherwise
    // land mid-scan and outside act(), which src/test/setup.ts turns into a hard failure.
    await act(async () => {
      await Promise.resolve()
    })
    // Wrap axe in act() — axe triggers DOM events that cause PatternFly Tabs
    // to schedule React state updates
    let results: Awaited<ReturnType<typeof axe>>
    await act(async () => {
      results = await axe(container, {
        rules: { 'aria-valid-attr-value': { enabled: false } },
      })
    })
    expect(results!).toHaveNoViolations()
  })
})
