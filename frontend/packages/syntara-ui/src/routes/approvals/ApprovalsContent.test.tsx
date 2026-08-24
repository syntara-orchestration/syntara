import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactElement } from 'react'
import { describe, expect, it, vi } from 'vitest'

import type { ProjectRead } from '../access/types'

import type { ApprovalWithDetails } from './Approvals'
import { ApprovalsContent, BulkActionDialogs } from './ApprovalsContent'

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

const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })

function renderWithProviders(ui: ReactElement) {
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>)
}

const mockApproval: ApprovalWithDetails = {
  id: 'a1',
  status: 'pending',
  created_at: '2024-01-01T00:00:00Z',
  decided_at: null,
  decided_by: null,
  decision_notes: null,
  execution_id: 'exec-1',
  approvalName: 'Test Approval',
  workflowName: 'Test Workflow',
  workflowId: 'wf-1',
  workflowVersion: 1,
  project_id: 'proj-1',
} as ApprovalWithDetails

const mockProject: ProjectRead = {
  id: 'proj-1',
  name: 'Project Alpha',
  description: null,
  created_at: '2024-01-01T00:00:00Z',
  updated_at: '2024-01-01T00:00:00Z',
}

const defaultTableProps = {
  sortedApprovals: [mockApproval],
  hasActiveFilters: false,
  handleClearAllFilters: vi.fn(),
  expandedRows: new Set<string>(),
  onToggleRow: vi.fn(),
  getSortParams: vi.fn(() => undefined),
  allRowsExpanded: false,
  collapseAllAriaLabel: 'Expand all',
  onCollapseAll: vi.fn(),
  hasExpandableRows: false,
  allPendingSelected: false,
  onSelectAll: vi.fn(),
  hasPendingApprovals: true,
  canDecideAnyApproval: true,
  isAllProjects: false,
  groupedApprovals: null,
  collapsedProjects: new Set<string>(),
  onToggleProject: vi.fn(),
  selectedApprovalIds: new Set<string>(),
  onSelectRow: vi.fn(),
  footerProps: { itemCount: 1, perPage: 20, page: 1, onSetPage: vi.fn(), onPerPageSelect: vi.fn() },
  approvalPermissions: new Map([['a1', true]]),
  isLoadingPermissions: false,
}

describe('ApprovalsContent', () => {
  it('renders no-data empty state when there are no approvals and no filters', () => {
    renderWithProviders(<ApprovalsContent {...defaultTableProps} sortedApprovals={[]} />)

    expect(screen.getByText('No approvals yet')).toBeInTheDocument()
    expect(screen.getByText(/No approvals are currently pending/i)).toBeInTheDocument()
  })

  it('renders filter empty state when filters are active but no approvals match', () => {
    const handleClearAllFilters = vi.fn()
    renderWithProviders(
      <ApprovalsContent
        {...defaultTableProps}
        sortedApprovals={[]}
        hasActiveFilters={true}
        handleClearAllFilters={handleClearAllFilters}
      />
    )

    expect(screen.getByText('No results found')).toBeInTheDocument()
  })

  it('renders flat table body when a single project is selected', () => {
    renderWithProviders(<ApprovalsContent {...defaultTableProps} isAllProjects={false} groupedApprovals={null} />)

    expect(screen.getByText('Test Approval')).toBeInTheDocument()
    expect(screen.getByRole('columnheader', { name: /Name/i })).toBeInTheDocument()
  })

  it('renders grouped table body when all projects are selected', () => {
    const groupedApprovals = new Map([['proj-1', { project: mockProject, approvals: [mockApproval] }]])

    renderWithProviders(
      <ApprovalsContent {...defaultTableProps} isAllProjects={true} groupedApprovals={groupedApprovals} />
    )

    expect(screen.getByText('Project Alpha')).toBeInTheDocument()
    expect(screen.getByText('Test Approval')).toBeInTheDocument()
  })
})

describe('BulkActionDialogs', () => {
  it('closes bulk approve dialog when Cancel is clicked', async () => {
    const user = userEvent.setup()
    const setBulkApproveDialogOpen = vi.fn()

    renderWithProviders(
      <BulkActionDialogs
        bulkApproveDialogOpen={true}
        setBulkApproveDialogOpen={setBulkApproveDialogOpen}
        bulkRejectDialogOpen={false}
        setBulkRejectDialogOpen={vi.fn()}
        handleBulkApprove={vi.fn()}
        handleBulkReject={vi.fn()}
        selectedCount={2}
        isBulkActionPending={false}
      />
    )

    await user.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(setBulkApproveDialogOpen).toHaveBeenCalledWith(false)
  })

  it('closes bulk reject dialog when Cancel is clicked', async () => {
    const user = userEvent.setup()
    const setBulkRejectDialogOpen = vi.fn()

    renderWithProviders(
      <BulkActionDialogs
        bulkApproveDialogOpen={false}
        setBulkApproveDialogOpen={vi.fn()}
        bulkRejectDialogOpen={true}
        setBulkRejectDialogOpen={setBulkRejectDialogOpen}
        handleBulkApprove={vi.fn()}
        handleBulkReject={vi.fn()}
        selectedCount={2}
        isBulkActionPending={false}
      />
    )

    await user.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(setBulkRejectDialogOpen).toHaveBeenCalledWith(false)
  })
})
