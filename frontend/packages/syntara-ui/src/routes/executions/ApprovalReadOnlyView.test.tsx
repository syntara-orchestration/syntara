import type { Approval } from '@syntara/contracts'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { axe } from 'vitest-axe'

import { ApprovalReadOnlyView } from './ApprovalReadOnlyView'

const mockApproval: Approval = {
  id: 'approval-1',
  created_at: '2026-04-15T10:00:00Z',
  updated_at: '2026-04-15T10:00:00Z',
  labels: {},
  execution_id: 'exec-4',
  approval_node_id: 'node-abc',
  name: 'Production Deployment Approval',
  description: 'Review before deploying',
  status: 'pending',
  workflow_context: {
    workflow_version_id: '1',
    workflow_name: 'Hello World Workflow',
    inputs: { environment: 'production' },
  },
  next_step_approved: { id: 'deploy', name: 'Deploy to Production', type: 'task' },
  next_step_rejected: { id: 'rollback', name: 'Rollback Staging', type: 'task' },
  decided_by: null,
  decided_at: null,
  decision_notes: null,
} as unknown as Approval

const defaultProps = {
  approval: mockApproval,
  approverUsernames: ['alice', 'bob'],
  approverGroups: ['platform-leads'],
  onClose: vi.fn(),
}

describe('ApprovalReadOnlyView', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders approval name and summary', () => {
    render(<ApprovalReadOnlyView {...defaultProps} />)

    expect(screen.getByText('Production Deployment Approval')).toBeInTheDocument()
    expect(screen.getByText('Hello World Workflow')).toBeInTheDocument()
  })

  it('shows authorization info alert', () => {
    render(<ApprovalReadOnlyView {...defaultProps} />)

    expect(screen.getByText('You are not authorized to approve or reject this request')).toBeInTheDocument()
  })

  it('displays approver usernames and groups in the alert', () => {
    render(<ApprovalReadOnlyView {...defaultProps} />)

    expect(screen.getByText(/Users: alice, bob/)).toBeInTheDocument()
    expect(screen.getByText(/Groups: platform-leads/)).toBeInTheDocument()
  })

  it('shows next steps for approved and rejected branches', () => {
    render(<ApprovalReadOnlyView {...defaultProps} />)

    expect(screen.getByText('If approved')).toBeInTheDocument()
    expect(screen.getByText('Deploy to Production')).toBeInTheDocument()
    expect(screen.getByText('If rejected')).toBeInTheDocument()
    expect(screen.getByText('Rollback Staging')).toBeInTheDocument()
  })

  it('does not render submit decision button', () => {
    render(<ApprovalReadOnlyView {...defaultProps} />)

    expect(screen.queryByRole('button', { name: /submit decision/i })).not.toBeInTheDocument()
  })

  it('renders close button and calls onClose when clicked', async () => {
    const user = userEvent.setup()
    const onClose = vi.fn()
    render(<ApprovalReadOnlyView {...defaultProps} onClose={onClose} />)

    await user.click(screen.getByRole('button', { name: 'Close' }))

    expect(onClose).toHaveBeenCalledOnce()
  })

  it('does not render approval decision toggle (approve/reject)', () => {
    render(<ApprovalReadOnlyView {...defaultProps} />)

    expect(screen.queryByRole('button', { name: 'Approve' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Reject' })).not.toBeInTheDocument()
  })

  it('shows "Workflow ends" when no rejected next step exists', () => {
    const approval = { ...mockApproval, next_step_rejected: null } as unknown as Approval
    render(<ApprovalReadOnlyView {...defaultProps} approval={approval} />)

    expect(screen.getByText('Workflow ends')).toBeInTheDocument()
  })

  it('uses activityNameMap to resolve node name', () => {
    const nameMap = new Map([['node-abc', 'Deploy Gate']])
    render(<ApprovalReadOnlyView {...defaultProps} activityNameMap={nameMap} />)

    expect(screen.getByText('Approval for Deploy Gate')).toBeInTheDocument()
  })

  it('has no accessibility violations', async () => {
    const { container } = render(<ApprovalReadOnlyView {...defaultProps} />)
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('does not show authorization alert when no approvers configured', () => {
    render(<ApprovalReadOnlyView {...defaultProps} approverUsernames={[]} approverGroups={[]} />)

    expect(screen.queryByText('You are not authorized to approve or reject this request')).not.toBeInTheDocument()
  })

  it('shows only usernames when no groups configured', () => {
    render(<ApprovalReadOnlyView {...defaultProps} approverGroups={[]} />)

    expect(screen.getByText(/Users: alice, bob/)).toBeInTheDocument()
    expect(screen.queryByText(/Groups:/)).not.toBeInTheDocument()
  })

  it('shows only groups when no usernames configured', () => {
    render(<ApprovalReadOnlyView {...defaultProps} approverUsernames={[]} />)

    expect(screen.getByText(/Groups: platform-leads/)).toBeInTheDocument()
    expect(screen.queryByText(/Users:/)).not.toBeInTheDocument()
  })

  it('uses approval.name when approval_node_id is null', () => {
    const approval = { ...mockApproval, approval_node_id: null } as unknown as Approval
    render(<ApprovalReadOnlyView {...defaultProps} approval={approval} />)

    expect(screen.getByText('Production Deployment Approval')).toBeInTheDocument()
    expect(screen.queryByText(/Approval for/)).not.toBeInTheDocument()
  })

  it('resolves next step names from activityNameMap', () => {
    const nameMap = new Map([
      ['deploy', 'Production Deployment'],
      ['rollback', 'Emergency Rollback'],
    ])
    render(<ApprovalReadOnlyView {...defaultProps} activityNameMap={nameMap} />)

    expect(screen.getByText('Production Deployment')).toBeInTheDocument()
    expect(screen.getByText('Emergency Rollback')).toBeInTheDocument()
  })

  it('renders approval context as JSON', async () => {
    render(<ApprovalReadOnlyView {...defaultProps} />)

    expect(screen.getByText('Approval context')).toBeInTheDocument()
    // JSON should contain approval data
    await waitFor(() => expect(screen.getByRole('code')).toHaveTextContent('"id"'))
    await waitFor(() => expect(screen.getByRole('code')).toHaveTextContent('"approval-1"'))
  })
})
