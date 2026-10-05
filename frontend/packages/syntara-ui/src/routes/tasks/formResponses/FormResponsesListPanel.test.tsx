import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { SynListPanel } from '../../../components/panels/list/SynListPanel'

import { FormResponsesListPanel } from './FormResponsesListPanel'

vi.mock('../../../hooks/useProjectSelector', () => ({
  useProjectSelector: () => ({
    selectedProjectId: null,
    stableProjectId: null,
    isAllProjects: true,
    projects: [],
  }),
}))

vi.mock('../../../hooks/useProjectsForGrouping', () => ({
  useProjectsForGrouping: () => [],
}))

vi.mock('../../../hooks/useCursorPagination', () => ({
  useCursorPagination: () => ({
    cursor: { page: 1, perPage: 20 },
    resetPagination: vi.fn(),
    filters: [],
    hasActiveFilters: false,
    queryParams: {},
    handleFilterChange: vi.fn(),
    handleClearAllFilters: vi.fn(),
    getFooterProps: () => ({}),
    getSortParams: () => undefined,
  }),
  useCursorReset: vi.fn(),
}))

vi.mock('./useFormResponsesData', () => ({
  useFormResponsesData: () => ({
    formPromptsQuery: { isPending: true, isFetching: false, error: null, refetch: vi.fn() },
    enrichedRows: [],
    groupedRows: null,
    sortedRows: [],
  }),
}))

describe('FormResponsesListPanel', () => {
  it('renders inside a tab panel when tab metadata is provided', () => {
    render(
      <SynListPanel>
        <FormResponsesListPanel tabKey="form-responses" tabLabel="Form responses" />
      </SynListPanel>
    )
    expect(screen.getByRole('tabpanel', { name: 'Form responses' })).toBeInTheDocument()
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
