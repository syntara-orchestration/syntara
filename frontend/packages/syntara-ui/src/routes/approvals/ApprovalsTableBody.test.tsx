import { Table } from '@patternfly/react-table'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { createElement } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import type { ProjectRead } from '../access/types'

import type { ApprovalWithDetails } from './Approvals'
import { FlatApprovalsTableBody, GroupedApprovalsTableBody } from './ApprovalsTableBody'

vi.mock('../../stores/useAuthStore', () => ({
  useAuthStore: (selector: (state: Record<string, unknown>) => unknown) =>
    selector({ username: 'testuser', userId: 'user-1' }),
}))

vi.mock('../../client', () => ({
  usersClient: {
    useQuery: vi.fn().mockReturnValue({ data: undefined, isLoading: false, error: null }),
  },
  authMiddleware: { onRequest: vi.fn() },
  interfaceTagMiddleware: { onRequest: vi.fn() },
}))

function createWrapper() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return ({ children }: { children: React.ReactNode }) =>
    createElement(QueryClientProvider, { client: queryClient }, children)
}

function makeApproval(overrides: Partial<ApprovalWithDetails> = {}): ApprovalWithDetails {
  return {
    id: 'approval-1',
    status: 'pending',
    created_at: '2026-07-01T10:00:00Z',
    decided_at: null,
    decided_by: null,
    decision_notes: null,
    execution_id: 'exec-1',
    approvalName: 'Test Approval',
    workflowName: 'Test Workflow',
    workflowId: 'wf-1',
    workflowVersion: 3,
    ...overrides,
  } as ApprovalWithDetails
}

function makeProject(overrides: Partial<ProjectRead> = {}): ProjectRead {
  return {
    id: 'proj-1',
    name: 'Project Alpha',
    ...overrides,
  } as ProjectRead
}

describe('FlatApprovalsTableBody', () => {
  const defaultProps = {
    approvals: [makeApproval()],
    expandedRows: new Set<string>(),
    onToggleRow: vi.fn(),
    approvalPermissions: new Map<string, boolean>(),
    isLoadingPermissions: false,
  }

  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders approval rows', () => {
    const Wrapper = createWrapper()
    render(
      <Wrapper>
        <Table aria-label="Approvals" isExpandable>
          <FlatApprovalsTableBody {...defaultProps} />
        </Table>
      </Wrapper>
    )

    expect(screen.getByText('Test Approval')).toBeInTheDocument()
    expect(screen.getByText('Test Workflow')).toBeInTheDocument()
  })

  it('renders approval name as link to execution', () => {
    const Wrapper = createWrapper()
    render(
      <Wrapper>
        <Table aria-label="Approvals" isExpandable>
          <FlatApprovalsTableBody {...defaultProps} />
        </Table>
      </Wrapper>
    )

    const approvalLink = screen.getByRole('link', { name: 'Test Approval' })
    expect(approvalLink).toHaveAttribute('href', '/executions/exec-1?approval=approval-1&history=closed')
  })

  it('renders workflow name as link to builder', () => {
    const Wrapper = createWrapper()
    render(
      <Wrapper>
        <Table aria-label="Approvals" isExpandable>
          <FlatApprovalsTableBody {...defaultProps} />
        </Table>
      </Wrapper>
    )

    const workflowLink = screen.getByRole('link', { name: 'Test Workflow' })
    expect(workflowLink).toHaveAttribute('href', '/workflow-builder/wf-1?version=3')
  })

  it('falls back to id when approvalName is missing', () => {
    const Wrapper = createWrapper()
    render(
      <Wrapper>
        <Table aria-label="Approvals" isExpandable>
          <FlatApprovalsTableBody {...defaultProps} approvals={[makeApproval({ approvalName: undefined })]} />
        </Table>
      </Wrapper>
    )

    expect(screen.getByText('approval-1')).toBeInTheDocument()
  })

  it('shows dash when workflowId is missing', () => {
    const Wrapper = createWrapper()
    render(
      <Wrapper>
        <Table aria-label="Approvals" isExpandable>
          <FlatApprovalsTableBody
            {...defaultProps}
            approvals={[makeApproval({ workflowId: undefined, workflowName: undefined })]}
          />
        </Table>
      </Wrapper>
    )

    expect(screen.getByText('—')).toBeInTheDocument()
  })

  it('shows expanded row content with approval notes for an approved decision', () => {
    const Wrapper = createWrapper()
    render(
      <Wrapper>
        <Table aria-label="Approvals" isExpandable>
          <FlatApprovalsTableBody
            {...defaultProps}
            approvals={[makeApproval({ status: 'approved', decision_notes: 'Looks good, approved.' })]}
            expandedRows={new Set(['approval-1'])}
          />
        </Table>
      </Wrapper>
    )

    expect(screen.getByText('Approval notes')).toBeInTheDocument()
    expect(screen.getByText('Looks good, approved.')).toBeInTheDocument()
  })

  it('shows expanded row content with rejection notes for a rejected decision', () => {
    const Wrapper = createWrapper()
    render(
      <Wrapper>
        <Table aria-label="Approvals" isExpandable>
          <FlatApprovalsTableBody
            {...defaultProps}
            approvals={[makeApproval({ status: 'rejected', decision_notes: 'Not ready yet.' })]}
            expandedRows={new Set(['approval-1'])}
          />
        </Table>
      </Wrapper>
    )

    expect(screen.getByText('Rejection notes')).toBeInTheDocument()
    expect(screen.getByText('Not ready yet.')).toBeInTheDocument()
  })

  it('does not render an expand toggle for a pending approval with no decision notes', () => {
    const Wrapper = createWrapper()
    render(
      <Wrapper>
        <Table aria-label="Approvals" isExpandable>
          <FlatApprovalsTableBody {...defaultProps} approvals={[makeApproval({ decision_notes: null })]} />
        </Table>
      </Wrapper>
    )

    expect(screen.queryByRole('button', { name: /details/i })).not.toBeInTheDocument()
  })

  it('does not render an expand toggle for a decided approval with no decision notes', () => {
    const Wrapper = createWrapper()
    render(
      <Wrapper>
        <Table aria-label="Approvals" isExpandable>
          <FlatApprovalsTableBody
            {...defaultProps}
            approvals={[makeApproval({ status: 'approved', decision_notes: null })]}
          />
        </Table>
      </Wrapper>
    )

    expect(screen.queryByRole('button', { name: /details/i })).not.toBeInTheDocument()
  })

  it('renders an expand toggle only for approvals with decision notes', () => {
    const Wrapper = createWrapper()
    render(
      <Wrapper>
        <Table aria-label="Approvals" isExpandable>
          <FlatApprovalsTableBody
            {...defaultProps}
            approvals={[
              makeApproval({ id: 'approval-1', status: 'pending', decision_notes: null }),
              makeApproval({ id: 'approval-2', status: 'approved', decision_notes: 'Approved after review.' }),
            ]}
          />
        </Table>
      </Wrapper>
    )

    expect(screen.getAllByRole('button', { name: /details/i })).toHaveLength(1)
  })

  it('renders "Actioned on" with UserTimestamp when decided_at is set', () => {
    const Wrapper = createWrapper()
    render(
      <Wrapper>
        <Table aria-label="Approvals" isExpandable>
          <FlatApprovalsTableBody
            {...defaultProps}
            approvals={[
              makeApproval({
                status: 'approved',
                decided_at: '2026-07-15T14:30:00Z',
                decided_by: { id: 'user-2', name: 'reviewer' },
              }),
            ]}
          />
        </Table>
      </Wrapper>
    )

    expect(screen.getByText('reviewer')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'reviewer' })).toBeInTheDocument()
  })

  it('renders "Actioned on" with timestamp only when decided_at is set but decided_by is null', () => {
    const Wrapper = createWrapper()
    const { container } = render(
      <Wrapper>
        <Table aria-label="Approvals" isExpandable>
          <FlatApprovalsTableBody
            {...defaultProps}
            approvals={[
              makeApproval({
                status: 'approved',
                decided_at: '2026-08-05T14:30:00Z',
                decided_by: null,
              }),
            ]}
          />
        </Table>
      </Wrapper>
    )

    expect(screen.getByText(/Aug 5/)).toBeInTheDocument()
    expect(container.textContent).not.toContain(' by ')
  })

  it('renders dash for "Actioned on" when decided_at is null', () => {
    const Wrapper = createWrapper()
    render(
      <Wrapper>
        <Table aria-label="Approvals" isExpandable>
          <FlatApprovalsTableBody
            {...defaultProps}
            approvals={[makeApproval({ decided_at: null, workflowId: 'wf-1' })]}
          />
        </Table>
      </Wrapper>
    )

    expect(screen.getByText('-')).toBeInTheDocument()
  })

  it('has no accessibility violations', async () => {
    const Wrapper = createWrapper()
    const { container } = render(
      <Wrapper>
        <Table aria-label="Approvals" isExpandable>
          <FlatApprovalsTableBody {...defaultProps} />
        </Table>
      </Wrapper>
    )

    expect(await axe(container)).toHaveNoViolations()
  })

  it('has no accessibility violations with an expanded row showing decision notes', async () => {
    const Wrapper = createWrapper()
    const { container } = render(
      <Wrapper>
        <Table aria-label="Approvals" isExpandable>
          <FlatApprovalsTableBody
            {...defaultProps}
            approvals={[makeApproval({ status: 'approved', decision_notes: 'Looks good, approved.' })]}
            expandedRows={new Set(['approval-1'])}
          />
        </Table>
      </Wrapper>
    )

    expect(await axe(container)).toHaveNoViolations()
  })
})

describe('GroupedApprovalsTableBody', () => {
  const approval = makeApproval()
  const project = makeProject()

  const groupedApprovals = new Map([['proj-1', { project, approvals: [approval] }]])

  const defaultProps = {
    groupedApprovals,
    collapsedProjects: new Set<string>(),
    onToggleProject: vi.fn(),
    expandedRows: new Set<string>(),
    onToggleRow: vi.fn(),
    approvalPermissions: new Map<string, boolean>(),
    isLoadingPermissions: false,
  }

  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders project group header with name and without count badge', () => {
    const Wrapper = createWrapper()
    render(
      <Wrapper>
        <Table aria-label="Approvals" isExpandable>
          <GroupedApprovalsTableBody {...defaultProps} />
        </Table>
      </Wrapper>
    )

    expect(screen.getByText('Project Alpha')).toBeInTheDocument()
    const groupHeader = screen.getByRole('row', { name: /Project Alpha/ })
    expect(within(groupHeader).queryByText('1')).not.toBeInTheDocument()
  })

  it('shows "No project" for unknown project id', () => {
    const grouped = new Map([['unknown', { project: null, approvals: [approval] }]])
    const Wrapper = createWrapper()
    render(
      <Wrapper>
        <Table aria-label="Approvals" isExpandable>
          <GroupedApprovalsTableBody {...defaultProps} groupedApprovals={grouped} />
        </Table>
      </Wrapper>
    )

    expect(screen.getByText('No project')).toBeInTheDocument()
  })

  it('hides approval rows when project is collapsed', () => {
    const Wrapper = createWrapper()
    render(
      <Wrapper>
        <Table aria-label="Approvals" isExpandable>
          <GroupedApprovalsTableBody {...defaultProps} collapsedProjects={new Set(['proj-1'])} />
        </Table>
      </Wrapper>
    )

    expect(screen.getByText('Project Alpha')).toBeInTheDocument()
    expect(screen.queryByText('Test Approval')).not.toBeInTheDocument()
  })

  it('calls onToggleProject when group header is clicked', async () => {
    const user = userEvent.setup()
    const onToggleProject = vi.fn()
    const Wrapper = createWrapper()
    render(
      <Wrapper>
        <Table aria-label="Approvals" isExpandable>
          <GroupedApprovalsTableBody {...defaultProps} onToggleProject={onToggleProject} />
        </Table>
      </Wrapper>
    )

    await user.click(screen.getByText('Project Alpha'))

    expect(onToggleProject).toHaveBeenCalledWith('proj-1')
  })

  it('falls back to projectId when project is null and id is not "unknown"', () => {
    const grouped = new Map([['proj-orphan', { project: null, approvals: [approval] }]])
    const Wrapper = createWrapper()
    render(
      <Wrapper>
        <Table aria-label="Approvals" isExpandable>
          <GroupedApprovalsTableBody {...defaultProps} groupedApprovals={grouped} />
        </Table>
      </Wrapper>
    )

    expect(screen.getByText('proj-orphan')).toBeInTheDocument()
  })

  it('has no accessibility violations', async () => {
    const Wrapper = createWrapper()
    const { container } = render(
      <Wrapper>
        <Table aria-label="Approvals" isExpandable>
          <GroupedApprovalsTableBody {...defaultProps} />
        </Table>
      </Wrapper>
    )

    expect(await axe(container)).toHaveNoViolations()
  })
})
