import type { Approval } from '@syntara/contracts'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactNode } from 'react'
import { axe } from 'vitest-axe'

import { approvalsClient } from '../../client'

import { ApprovalReviewView } from './ApprovalReviewView'

function createWrapper() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  )
}

const mockMutate = vi.fn()
const mockShowAlert = vi.fn()
const mockShowSuccess = vi.fn()

vi.mock('../../client', () => ({
  approvalsClient: {
    useMutation: vi.fn(() => ({
      mutate: mockMutate,
      isPending: false,
    })),
  },
  usersClient: {
    useQuery: vi.fn(() => ({
      data: undefined,
      isLoading: false,
    })),
  },
  authMiddleware: { onRequest: vi.fn() },
  interfaceTagMiddleware: { onRequest: vi.fn() },
}))

vi.mock('../access/accessClient', () => ({
  accessFetchClient: { POST: vi.fn(() => Promise.resolve({ data: { allowed: true } })) },
}))

vi.mock('../../providers/alerts', () => ({
  useAlerts: () => ({
    showAlert: mockShowAlert,
    showSuccess: mockShowSuccess,
  }),
}))

vi.mock('../../hooks/useFormMutationErrorHandler', () => ({
  useFormMutationErrorHandler: () => () => vi.fn(),
}))

vi.mock('../../stores/useAuthStore', () => ({
  useAuthStore: vi.fn((selector: (state: { username: string; userId: string }) => unknown) => {
    const state = { username: 'testuser', userId: 'test-user-id' }

    return selector(state)
  }),
}))

const mockCanDecide = vi.fn(() => true)
vi.mock('../approvals/useCanDecideApproval', () => ({
  useCanDecideApproval: vi.fn(() => ({
    canDecide: mockCanDecide(),
    isLoading: false,
  })),
}))

// Mock useApprovalPermissions to return allowed by default
vi.mock('../approvals/useApprovalPermissions', () => ({
  useApprovalPermissions: vi.fn(() => ({
    canRead: true,
    canDecide: true, // Default: RBAC permission allowed
    isChecking: false,
    tooltips: {
      decide: 'To decide on approvals, you need a role with the approval:decide policy.',
    },
  })),
}))

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
  approver_users: [],
  approver_groups: [],
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
  onClose: vi.fn(),
}

describe('ApprovalReviewView', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockMutate.mockReset()
    mockCanDecide.mockReturnValue(true) // Default: user can decide
    vi.mocked(approvalsClient.useMutation).mockReturnValue({
      mutate: mockMutate,
      isPending: false,
    })
  })

  it('renders approval name, summary list, context, and form', () => {
    render(<ApprovalReviewView {...defaultProps} />, { wrapper: createWrapper() })

    expect(screen.getByRole('heading', { name: 'Production Deployment Approval' })).toBeInTheDocument()
    expect(screen.getByText('Approval type')).toBeInTheDocument()
    expect(screen.getByText('Hello World Workflow')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Approval context' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Decision' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Approve' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Reject' })).toBeInTheDocument()
    expect(screen.getByRole('textbox', { name: 'Decision notes' })).toBeInTheDocument()
  })

  it('renders next steps showing what happens on approve and reject', () => {
    const approvalWithSteps = {
      ...mockApproval,
      next_step_approved: { id: 'deploy', name: 'Deploy to Production', type: 'task' },
      next_step_rejected: { id: 'rollback', name: 'Rollback Staging', type: 'task' },
    } as unknown as Approval

    render(<ApprovalReviewView {...defaultProps} approval={approvalWithSteps} />, { wrapper: createWrapper() })

    expect(screen.getByText('Next steps')).toBeInTheDocument()
    expect(screen.getByText('If approved')).toBeInTheDocument()
    expect(screen.getByText('Deploy to Production')).toBeInTheDocument()
    expect(screen.getByText('If rejected')).toBeInTheDocument()
    expect(screen.getByText('Rollback Staging')).toBeInTheDocument()
  })

  it('shows "Workflow ends" when no rejected step exists', () => {
    const approvalNoReject = {
      ...mockApproval,
      next_step_approved: { id: 'deploy', name: 'Deploy to Production', type: 'task' },
      next_step_rejected: null,
    } as unknown as Approval

    render(<ApprovalReviewView {...defaultProps} approval={approvalNoReject} />, { wrapper: createWrapper() })

    expect(screen.getByText('Workflow ends')).toBeInTheDocument()
  })

  it('defaults to Approve', () => {
    render(<ApprovalReviewView {...defaultProps} />, { wrapper: createWrapper() })

    expect(screen.getByRole('button', { name: 'Approve' })).toHaveClass('pf-m-selected')
  })

  it('calls onClose when Cancel is clicked', async () => {
    const user = userEvent.setup()
    const onClose = vi.fn()

    render(<ApprovalReviewView {...defaultProps} onClose={onClose} />, { wrapper: createWrapper() })

    await user.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(onClose).toHaveBeenCalledOnce()
  })

  it('submits with null notes when notes field is empty', async () => {
    const user = userEvent.setup()

    render(<ApprovalReviewView {...defaultProps} />, { wrapper: createWrapper() })

    await user.click(screen.getByRole('button', { name: 'Submit decision' }))

    expect(mockMutate).toHaveBeenCalledWith(
      expect.objectContaining({
        body: { status: 'approved', notes: null },
      }),
      expect.any(Object)
    )
  })

  it('calls mutation with correct body on Approve', async () => {
    const user = userEvent.setup()

    render(<ApprovalReviewView {...defaultProps} />, { wrapper: createWrapper() })

    await user.type(screen.getByRole('textbox', { name: 'Decision notes' }), 'Looks good to deploy')
    await user.click(screen.getByRole('button', { name: 'Submit decision' }))

    expect(mockMutate).toHaveBeenCalledWith(
      {
        params: { path: { approval_id: 'approval-1' } },
        body: {
          status: 'approved',
          notes: 'Looks good to deploy',
        },
      },
      expect.objectContaining({
        onSuccess: expect.any(Function) as unknown,
        onError: expect.any(Function) as unknown,
      })
    )
  })

  it('toggles between Approve and Reject', async () => {
    const user = userEvent.setup()

    render(<ApprovalReviewView {...defaultProps} />, { wrapper: createWrapper() })

    expect(screen.getByRole('button', { name: 'Approve' })).toHaveClass('pf-m-selected')

    await user.click(screen.getByRole('button', { name: 'Reject' }))
    expect(screen.getByRole('button', { name: 'Reject' })).toHaveClass('pf-m-selected')

    await user.click(screen.getByRole('button', { name: 'Approve' }))
    expect(screen.getByRole('button', { name: 'Approve' })).toHaveClass('pf-m-selected')
  })

  it('calls onClose on successful mutation', async () => {
    const user = userEvent.setup()
    const onClose = vi.fn()
    mockMutate.mockImplementation((_data: unknown, callbacks: { onSuccess: () => void }) => {
      callbacks.onSuccess()
    })

    render(<ApprovalReviewView {...defaultProps} onClose={onClose} />, { wrapper: createWrapper() })

    await user.type(screen.getByRole('textbox', { name: 'Decision notes' }), 'Approved')
    await user.click(screen.getByRole('button', { name: 'Submit decision' }))

    expect(onClose).toHaveBeenCalledOnce()
    expect(mockShowSuccess).toHaveBeenCalledWith(
      expect.objectContaining({
        title: 'Approval submitted',
      })
    )
  })

  it('disables submit button while mutation is pending', () => {
    vi.mocked(approvalsClient.useMutation).mockReturnValue({
      mutate: mockMutate,
      isPending: true,
    })

    render(<ApprovalReviewView {...defaultProps} />, { wrapper: createWrapper() })

    const submitButton = screen.getByRole('button', { name: /Submit decision/i })
    expect(submitButton).toBeDisabled()
  })

  describe('Permission-based rendering', () => {
    it('shows read-only view when user cannot decide approval', () => {
      mockCanDecide.mockReturnValue(false)

      const approvalWithApprovers = {
        ...mockApproval,
        approver_users: [
          { id: 'user-1', username: 'alice' },
          { id: 'user-2', username: 'bob' },
        ],
        approver_groups: [{ id: 'group-1', name: 'admins' }],
      } as unknown as Approval

      render(<ApprovalReviewView {...defaultProps} approval={approvalWithApprovers} />, { wrapper: createWrapper() })

      // Should show read-only view header
      expect(screen.getByRole('heading', { name: 'Production Deployment Approval' })).toBeInTheDocument()

      // Should NOT show the decision form controls
      expect(screen.queryByRole('button', { name: /Submit decision/i })).not.toBeInTheDocument()

      // Should show approver information in read-only alert
      expect(screen.getByText(/This approval is restricted to:/)).toBeInTheDocument()
      expect(screen.getByText(/Users: alice, bob/)).toBeInTheDocument()
      expect(screen.getByText(/Groups: admins/)).toBeInTheDocument()
    })

    it('shows decision form when user can decide approval', () => {
      mockCanDecide.mockReturnValue(true)

      render(<ApprovalReviewView {...defaultProps} />, { wrapper: createWrapper() })

      // Should show decision form controls
      expect(screen.getByRole('button', { name: /Submit decision/i })).toBeInTheDocument()
      expect(screen.getByText('Decision')).toBeInTheDocument()

      // Should NOT show approver information (that's in read-only view)
      expect(screen.queryByText('Approver users')).not.toBeInTheDocument()
    })
  })

  it('has no accessibility violations', async () => {
    const { container } = render(<ApprovalReviewView {...defaultProps} />, { wrapper: createWrapper() })

    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })
})
