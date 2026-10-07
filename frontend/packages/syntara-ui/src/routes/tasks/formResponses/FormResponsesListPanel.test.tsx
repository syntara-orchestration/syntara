import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { SynListPanel } from '../../../components/panels/list/SynListPanel'

import { FormResponsesListPanel } from './FormResponsesListPanel'

type MockProjectSelectorState = {
  selectedProjectId: string | null
  stableProjectId: string | null
  isAllProjects: boolean
  projects: { id: string; name: string }[]
  ProjectSelector: null
}

const defaultProjectSelectorState: MockProjectSelectorState = {
  selectedProjectId: null,
  stableProjectId: null,
  isAllProjects: true,
  projects: [],
  ProjectSelector: null,
}

const mockUseProjectSelector = vi.hoisted(() => vi.fn((): MockProjectSelectorState => defaultProjectSelectorState))

vi.mock('../../../hooks/useProjectSelector', () => ({
  useProjectSelector: mockUseProjectSelector,
}))

vi.mock('../../../hooks/useProjectsForGrouping', () => ({
  useProjectsForGrouping: () => [],
}))

const mockUseCursorPagination = vi.hoisted(() => vi.fn())

vi.mock('../../../hooks/useCursorPagination', () => ({
  useCursorPagination: mockUseCursorPagination,
  useCursorReset: vi.fn(),
}))

const mockUseFormResponsesData = vi.hoisted(() => vi.fn())

const mockFormsUseQuery = vi.hoisted(() => vi.fn())

vi.mock('../../../client', () => ({
  formsClient: {
    useQuery: mockFormsUseQuery,
  },
}))

vi.mock('./useFormResponsesData', () => ({
  useFormResponsesData: mockUseFormResponsesData,
}))

const sampleRow = {
  id: 'fp-1',
  execution_id: 'exec-1',
  project_id: 'proj-1',
  name: 'Collect input',
  status: 'pending' as const,
  workflow_name: 'Onboarding',
  workflowName: 'Onboarding',
  created_at: '2026-01-01T00:00:00Z',
}

describe('FormResponsesListPanel', () => {
  beforeEach(() => {
    mockUseProjectSelector.mockReturnValue(defaultProjectSelectorState)
    mockFormsUseQuery.mockReturnValue({ isLoading: false, isError: false, data: undefined, refetch: vi.fn() })
    mockUseCursorPagination.mockReturnValue({
      cursor: { page: 1, perPage: 20 },
      resetPagination: vi.fn(),
      filters: [],
      hasActiveFilters: false,
      queryParams: {},
      handleFilterChange: vi.fn(),
      handleClearAllFilters: vi.fn(),
      getFooterProps: () => ({
        page: 1,
        perPage: 20,
        hasNext: false,
        onPrev: vi.fn(),
        onNext: vi.fn(),
        onPerPageChange: vi.fn(),
      }),
      getSortParams: () => undefined,
    })
    mockUseFormResponsesData.mockReturnValue({
      formPromptsQuery: { isPending: true, isFetching: false, error: null, refetch: vi.fn(), data: undefined },
      enrichedRows: [],
      groupedRows: null,
      sortedRows: [],
    })
  })

  it('renders inside a tab panel when tab metadata is provided', () => {
    render(
      <SynListPanel>
        <FormResponsesListPanel tabKey="form-responses" tabLabel="Form responses" />
      </SynListPanel>
    )
    expect(screen.getByRole('tabpanel', { name: 'Form responses' })).toBeInTheDocument()
  })

  it('renders the table when rows are loaded', () => {
    mockUseFormResponsesData.mockReturnValue({
      formPromptsQuery: {
        isPending: false,
        isFetching: false,
        error: null,
        refetch: vi.fn(),
        data: { resources: [sampleRow] },
      },
      enrichedRows: [sampleRow],
      groupedRows: new Map([['proj-1', { project: null, rows: [sampleRow] }]]),
      sortedRows: [sampleRow],
    })

    render(
      <SynListPanel>
        <FormResponsesListPanel />
      </SynListPanel>
    )

    expect(screen.getByText('Collect input')).toBeInTheDocument()
    expect(screen.getByRole('columnheader', { name: 'Name' })).toBeInTheDocument()
  })

  it('shows filters when rows are empty but filters are active', () => {
    mockUseCursorPagination.mockReturnValue({
      cursor: { page: 1, perPage: 20 },
      resetPagination: vi.fn(),
      filters: [{ id: 'name', value: 'x' }],
      hasActiveFilters: true,
      queryParams: { name: 'x' },
      handleFilterChange: vi.fn(),
      handleClearAllFilters: vi.fn(),
      getFooterProps: () => ({
        page: 1,
        perPage: 20,
        hasNext: false,
        onPrev: vi.fn(),
        onNext: vi.fn(),
        onPerPageChange: vi.fn(),
      }),
      getSortParams: () => undefined,
    })
    mockUseFormResponsesData.mockReturnValue({
      formPromptsQuery: { isPending: false, isFetching: false, error: null, refetch: vi.fn(), data: { resources: [] } },
      enrichedRows: [],
      groupedRows: new Map(),
      sortedRows: [],
    })

    render(
      <SynListPanel>
        <FormResponsesListPanel />
      </SynListPanel>
    )

    expect(screen.getByRole('search', { name: 'Filters' })).toBeInTheDocument()
  })

  it('shows an error state with retry when the query fails', () => {
    const refetch = vi.fn()
    mockUseFormResponsesData.mockReturnValue({
      formPromptsQuery: {
        isPending: false,
        isFetching: false,
        error: { title: 'Failed', detail: 'Server error', retryable: true },
        refetch,
        data: undefined,
      },
      enrichedRows: [],
      groupedRows: null,
      sortedRows: [],
    })

    render(
      <SynListPanel>
        <FormResponsesListPanel />
      </SynListPanel>
    )

    expect(screen.getByText('Error loading form responses')).toBeInTheDocument()
  })

  it('toggles expand-all and project group collapse when data is loaded', async () => {
    const row2 = { ...sampleRow, id: 'fp-2', name: 'Second prompt' }
    mockUseFormResponsesData.mockReturnValue({
      formPromptsQuery: {
        isPending: false,
        isFetching: false,
        error: null,
        refetch: vi.fn(),
        data: { resources: [sampleRow, row2] },
      },
      enrichedRows: [sampleRow, row2],
      groupedRows: new Map([['proj-1', { project: { id: 'proj-1', name: 'Project A' }, rows: [sampleRow, row2] }]]),
      sortedRows: [sampleRow, row2],
    })

    const user = userEvent.setup()
    render(
      <SynListPanel>
        <FormResponsesListPanel />
      </SynListPanel>
    )

    await user.click(screen.getByRole('button', { name: /expand all/i }))
    expect(screen.getAllByRole('link', { name: 'Collect input' }).length).toBeGreaterThan(0)

    await user.click(screen.getByRole('button', { name: /expand all/i }))

    await user.click(screen.getByText('Project A'))
    expect(screen.queryByRole('link', { name: 'Collect input' })).not.toBeInTheDocument()
  })

  it('renders a flat list when a single project is selected', () => {
    mockUseProjectSelector.mockReturnValue({
      ...defaultProjectSelectorState,
      selectedProjectId: 'proj-1',
      stableProjectId: 'proj-1',
      isAllProjects: false,
      projects: [{ id: 'proj-1', name: 'Project A' }],
    })
    mockUseFormResponsesData.mockReturnValue({
      formPromptsQuery: {
        isPending: false,
        isFetching: false,
        error: null,
        refetch: vi.fn(),
        data: { resources: [sampleRow] },
      },
      enrichedRows: [sampleRow],
      groupedRows: null,
      sortedRows: [sampleRow],
    })

    render(
      <SynListPanel>
        <FormResponsesListPanel />
      </SynListPanel>
    )

    expect(screen.getByRole('link', { name: 'Collect input' })).toBeInTheDocument()
    expect(screen.queryByText('Project A')).not.toBeInTheDocument()
  })

  it('has no accessibility violations while loading', async () => {
    const { container } = render(
      <SynListPanel>
        <FormResponsesListPanel />
      </SynListPanel>
    )
    expect(await axe(container)).toHaveNoViolations()
  })
})
