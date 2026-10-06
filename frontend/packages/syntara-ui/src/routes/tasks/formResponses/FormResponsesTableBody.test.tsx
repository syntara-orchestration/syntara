import { Table } from '@patternfly/react-table'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { createElement } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import type { ProjectRead } from '../../access/types'

import { FlatFormResponsesTableBody, GroupedFormResponsesTableBody } from './FormResponsesTableBody'
import type { FormResponseListRow } from './useFormResponsesData'

const mockUseQuery = vi.hoisted(() => vi.fn())

vi.mock('../../../client', () => ({
  formsClient: {
    useQuery: mockUseQuery,
  },
}))

function createWrapper() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return ({ children }: { children: React.ReactNode }) =>
    createElement(QueryClientProvider, { client: queryClient }, children)
}

function makeRow(overrides: Partial<FormResponseListRow> = {}): FormResponseListRow {
  return {
    id: 'fp-1',
    execution_id: 'exec-1',
    project_id: 'proj-1',
    prompt_node_id: 'node-1',
    name: 'Collect input',
    status: 'pending',
    workflow_name: 'Onboarding',
    workflowName: 'Onboarding',
    workflowId: 'wf-1',
    workflowVersion: 2,
    created_at: '2026-01-01T00:00:00Z',
    ...overrides,
  }
}

function makeProject(overrides: Partial<ProjectRead> = {}): ProjectRead {
  return {
    id: 'proj-1',
    name: 'Project Alpha',
    ...overrides,
  }
}

describe('FlatFormResponsesTableBody', () => {
  const defaultProps = {
    rows: [makeRow()],
    expandedRows: new Set<string>(),
    onToggleRow: vi.fn(),
  }

  beforeEach(() => {
    vi.clearAllMocks()
    mockUseQuery.mockReturnValue({ isLoading: false, isError: false, data: undefined })
  })

  it('uses the row id as the name link label when name is empty', () => {
    const Wrapper = createWrapper()
    render(
      <Wrapper>
        <Table aria-label="Form responses" isExpandable>
          <FlatFormResponsesTableBody {...defaultProps} rows={[makeRow({ name: '' })]} />
        </Table>
      </Wrapper>
    )

    expect(screen.getByRole('link', { name: 'fp-1' })).toBeInTheDocument()
  })

  it('renders row cells and workflow link', () => {
    const Wrapper = createWrapper()
    render(
      <Wrapper>
        <Table aria-label="Form responses" isExpandable>
          <FlatFormResponsesTableBody {...defaultProps} />
        </Table>
      </Wrapper>
    )

    expect(screen.getByRole('link', { name: 'Collect input' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Onboarding' })).toBeInTheDocument()
    expect(screen.getByText('Pending')).toBeInTheDocument()
  })

  it('shows an em dash for workflow when workflowId is missing', () => {
    const Wrapper = createWrapper()
    render(
      <Wrapper>
        <Table aria-label="Form responses" isExpandable>
          <FlatFormResponsesTableBody
            {...defaultProps}
            rows={[makeRow({ workflowId: null, workflowName: undefined, workflow_name: undefined })]}
          />
        </Table>
      </Wrapper>
    )

    expect(screen.getByText('—')).toBeInTheDocument()
  })

  it('renders responded_by timestamp when responded_at is set', () => {
    const Wrapper = createWrapper()
    render(
      <Wrapper>
        <Table aria-label="Form responses" isExpandable>
          <FlatFormResponsesTableBody
            {...defaultProps}
            rows={[
              makeRow({
                status: 'submitted',
                responded_at: '2026-02-01T12:00:00Z',
                responded_by: { id: 'user-1', name: 'operator', type: 'user' },
              }),
            ]}
          />
        </Table>
      </Wrapper>
    )

    expect(screen.getByText('operator')).toBeInTheDocument()
  })

  it('calls onToggleRow when expand is toggled', async () => {
    const user = userEvent.setup()
    const onToggleRow = vi.fn()
    const Wrapper = createWrapper()

    render(
      <Wrapper>
        <Table aria-label="Form responses" isExpandable>
          <FlatFormResponsesTableBody {...defaultProps} onToggleRow={onToggleRow} />
        </Table>
      </Wrapper>
    )

    await user.click(screen.getByRole('button', { name: /details/i }))
    expect(onToggleRow).toHaveBeenCalledWith('fp-1')
  })

  it('renders expanded detail when the row is open', () => {
    mockUseQuery.mockReturnValue({
      isLoading: false,
      isError: false,
      data: { message: 'Fill this in', response_data: { ok: true } },
    })
    const Wrapper = createWrapper()
    render(
      <Wrapper>
        <Table aria-label="Form responses" isExpandable>
          <FlatFormResponsesTableBody {...defaultProps} expandedRows={new Set(['fp-1'])} />
        </Table>
      </Wrapper>
    )

    expect(screen.getByText('Fill this in')).toBeInTheDocument()
  })

  it('links to the workflow builder when workflowId is set without a version', () => {
    const Wrapper = createWrapper()
    render(
      <Wrapper>
        <Table aria-label="Form responses" isExpandable>
          <FlatFormResponsesTableBody
            {...defaultProps}
            rows={[makeRow({ workflowId: 'wf-only', workflowVersion: null, workflowName: 'Versionless' })]}
          />
        </Table>
      </Wrapper>
    )

    const link = screen.getByRole('link', { name: 'Versionless' })
    expect(link).toHaveAttribute('href', expect.stringContaining('wf-only'))
  })

  it('renders workflow name without a link when workflowId is absent', () => {
    const Wrapper = createWrapper()
    render(
      <Wrapper>
        <Table aria-label="Form responses" isExpandable>
          <FlatFormResponsesTableBody
            {...defaultProps}
            rows={[makeRow({ workflowId: null, workflow_name: 'Manual workflow', workflowName: 'Manual workflow' })]}
          />
        </Table>
      </Wrapper>
    )

    expect(screen.getByText('Manual workflow')).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Manual workflow' })).not.toBeInTheDocument()
  })

  it('renders dash for actioned on when responded_at is missing', () => {
    const Wrapper = createWrapper()
    render(
      <Wrapper>
        <Table aria-label="Form responses" isExpandable>
          <FlatFormResponsesTableBody {...defaultProps} rows={[makeRow({ responded_at: undefined })]} />
        </Table>
      </Wrapper>
    )

    expect(screen.getByText('-')).toBeInTheDocument()
  })

  it('has no accessibility violations', async () => {
    const Wrapper = createWrapper()
    const { container } = render(
      <Wrapper>
        <Table aria-label="Form responses" isExpandable>
          <FlatFormResponsesTableBody {...defaultProps} />
        </Table>
      </Wrapper>
    )

    expect(await axe(container)).toHaveNoViolations()
  })
})

describe('GroupedFormResponsesTableBody', () => {
  const row = makeRow()
  const project = makeProject()
  const groupedRows = new Map([['proj-1', { project, rows: [row] }]])

  beforeEach(() => {
    mockUseQuery.mockReturnValue({ isLoading: false, isError: false, data: undefined })
  })

  it('renders project group header and rows when expanded', () => {
    const Wrapper = createWrapper()
    render(
      <Wrapper>
        <Table aria-label="Form responses" isExpandable>
          <GroupedFormResponsesTableBody
            groupedRows={groupedRows}
            collapsedProjects={new Set()}
            onToggleProject={vi.fn()}
            expandedRows={new Set()}
            onToggleRow={vi.fn()}
          />
        </Table>
      </Wrapper>
    )

    expect(screen.getByText('Project Alpha')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Collect input' })).toBeInTheDocument()
  })

  it('hides rows when the project group is collapsed', () => {
    const Wrapper = createWrapper()
    render(
      <Wrapper>
        <Table aria-label="Form responses" isExpandable>
          <GroupedFormResponsesTableBody
            groupedRows={groupedRows}
            collapsedProjects={new Set(['proj-1'])}
            onToggleProject={vi.fn()}
            expandedRows={new Set()}
            onToggleRow={vi.fn()}
          />
        </Table>
      </Wrapper>
    )

    expect(screen.getByText('Project Alpha')).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Collect input' })).not.toBeInTheDocument()
  })

  it('calls onToggleProject when the group header is clicked', async () => {
    const onToggleProject = vi.fn()
    const user = userEvent.setup()
    const Wrapper = createWrapper()
    render(
      <Wrapper>
        <Table aria-label="Form responses" isExpandable>
          <GroupedFormResponsesTableBody
            groupedRows={groupedRows}
            collapsedProjects={new Set()}
            onToggleProject={onToggleProject}
            expandedRows={new Set()}
            onToggleRow={vi.fn()}
          />
        </Table>
      </Wrapper>
    )

    await user.click(screen.getByText('Project Alpha'))
    expect(onToggleProject).toHaveBeenCalledWith('proj-1')
  })

  it('shows the project id when the project record is missing', () => {
    const group = new Map([['proj-9', { project: null, rows: [row] }]])
    const Wrapper = createWrapper()
    render(
      <Wrapper>
        <Table aria-label="Form responses" isExpandable>
          <GroupedFormResponsesTableBody
            groupedRows={group}
            collapsedProjects={new Set()}
            onToggleProject={vi.fn()}
            expandedRows={new Set()}
            onToggleRow={vi.fn()}
          />
        </Table>
      </Wrapper>
    )

    expect(screen.getByText('proj-9')).toBeInTheDocument()
  })

  it('labels unknown projects', () => {
    const unknownGroup = new Map([['unknown', { project: null, rows: [row] }]])
    const Wrapper = createWrapper()
    render(
      <Wrapper>
        <Table aria-label="Form responses" isExpandable>
          <GroupedFormResponsesTableBody
            groupedRows={unknownGroup}
            collapsedProjects={new Set()}
            onToggleProject={vi.fn()}
            expandedRows={new Set()}
            onToggleRow={vi.fn()}
          />
        </Table>
      </Wrapper>
    )

    expect(screen.getByText('No project')).toBeInTheDocument()
  })
})
