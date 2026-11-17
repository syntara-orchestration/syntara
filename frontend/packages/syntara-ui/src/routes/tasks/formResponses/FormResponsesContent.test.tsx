import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { createElement, type ComponentProps } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import type { PaginationFooterProps } from '../../../components/table/PaginationFooter'

import { FormResponsesContent } from './FormResponsesContent'
import type { FormResponseListRow } from './useFormResponsesData'

vi.mock('../../../client', () => ({
  formsClient: {
    useQuery: vi.fn().mockReturnValue({ isLoading: false, isError: false, data: undefined }),
  },
}))

const baseRow: FormResponseListRow = {
  id: 'fp-1',
  execution_id: 'exec-1',
  project_id: 'proj-1',
  prompt_node_id: 'node-1',
  name: 'Collect input',
  status: 'pending',
  workflow_name: 'Onboarding',
  workflowName: 'Onboarding',
  workflowId: 'wf-1',
  created_at: '2026-01-01T00:00:00Z',
}

const sharedProps = {
  sortedRows: [baseRow],
  expandedRows: new Set<string>(),
  onToggleRow: vi.fn(),
  getSortParams: () => undefined,
  allRowsExpanded: false,
  collapseAllAriaLabel: 'Expand all',
  onCollapseAll: vi.fn(),
  collapsedProjects: new Set<string>(),
  onToggleProject: vi.fn(),
  footerProps: {
    page: 1,
    perPage: 20,
    hasNext: false,
    onPrev: vi.fn(),
    onNext: vi.fn(),
    onPerPageChange: vi.fn(),
  } satisfies PaginationFooterProps,
}

function renderContent(props: ComponentProps<typeof FormResponsesContent>) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const Wrapper = ({ children }: { children: React.ReactNode }) =>
    createElement(QueryClientProvider, { client: queryClient }, children)
  return render(
    <Wrapper>
      <FormResponsesContent {...props} />
    </Wrapper>
  )
}

describe('FormResponsesContent', () => {
  it('renders the flat table body when a single project is selected', () => {
    renderContent({
      ...sharedProps,
      isAllProjects: false,
      groupedRows: null,
    })

    expect(screen.getByRole('columnheader', { name: 'Name' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Collect input' })).toBeInTheDocument()
  })

  it('renders the grouped table body when all projects is selected', () => {
    const groupedRows = new Map([['proj-1', { project: { id: 'proj-1', name: 'Project A' }, rows: [baseRow] }]])

    renderContent({
      ...sharedProps,
      isAllProjects: true,
      groupedRows,
    })

    expect(screen.getByText('Project A')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Collect input' })).toBeInTheDocument()
  })

  it('uses the flat body when all projects is selected but grouped rows are unavailable', () => {
    renderContent({
      ...sharedProps,
      isAllProjects: true,
      groupedRows: null,
    })

    expect(screen.getByRole('link', { name: 'Collect input' })).toBeInTheDocument()
    expect(screen.queryByText('Project A')).not.toBeInTheDocument()
  })

  it('has no accessibility violations', async () => {
    const { container } = renderContent({ ...sharedProps, isAllProjects: false, groupedRows: null })
    expect(await axe(container)).toHaveNoViolations()
  })
})
