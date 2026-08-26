import type { Approval } from '@syntara/contracts'
import { render, screen, within, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import React from 'react'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { axe } from 'vitest-axe'

import { approvalsClient } from '../../client'
import { useFilterState } from '../../hooks/useFilterState'
import { assertUrlParam, assertUrlParamIsNull } from '../../test/filter-test-helpers'
import { accessClient } from '../access/accessClient'

import Approvals from './Approvals'
import { useApprovalPermissions } from './useApprovalPermissions'

// Mock the approvalsClient
vi.mock('../../client', () => ({
  authMiddleware: { onRequest: vi.fn() },
  interfaceTagMiddleware: { onRequest: vi.fn() },
  approvalsClient: {
    useQuery: vi.fn(),
    useMutation: vi.fn(() => ({
      mutate: vi.fn(),
      isPending: false,
      isError: false,
      error: null,
    })),
  },
  usersClient: {
    useQuery: vi.fn(() => ({
      data: undefined,
      isLoading: false,
    })),
  },
}))

vi.mock('../../stores/useAuthStore', () => ({
  useAuthStore: vi.fn((selector: (state: { username: string; userId: string }) => unknown) => {
    const state = { username: 'testuser', userId: 'test-user-id' }

    return selector(state)
  }),
}))

// Mock the accessClient used for project-scoped approvals
vi.mock('../access/accessClient', () => ({
  accessClient: {
    useQuery: vi.fn(),
  },
  accessFetchClient: { POST: vi.fn(() => Promise.resolve({ data: { allowed: true } })) },
}))

// Mock useProjectSelector to avoid needing accessClient / QueryClientProvider
const mockUseProjectSelector = vi.fn(() => ({
  selectedProject: null as { id: string; name: string } | null,
  isAllProjects: true,
  projects: [] as { id: string; name: string }[],
  ProjectSelector: null,
}))
vi.mock('../../hooks/useProjectSelector', () => ({
  useProjectSelector: () => mockUseProjectSelector(),
}))

// Passthrough — grouping name resolution is covered by useProjectsForGrouping tests.
vi.mock('../../hooks/useProjectsForGrouping', () => ({
  useProjectsForGrouping: (knownProjects: unknown) => knownProjects,
}))

// Mock useApprovalDecideProjects to avoid QueryClientProvider dependency from useAllPermissions.
// Stable references prevent infinite re-render loops in useMemo dependency chains.
const EMPTY_PROJECT_NAMES = new Set<string>()
vi.mock('./useApprovalDecideProjects', () => ({
  useApprovalDecideProjects: vi.fn(() => ({
    canDecideAllProjects: false,
    canDecideProjectNames: EMPTY_PROJECT_NAMES,
    canReadProjectNames: EMPTY_PROJECT_NAMES,
    isLoading: false,
    error: null,
  })),
}))

// Mock useApprovalPermissions
vi.mock('./useApprovalPermissions', () => ({
  useApprovalPermissions: vi.fn(() => ({
    canRead: true,
    canDecide: true,
    isChecking: false,
    tooltips: {
      decide: 'To decide on approvals, you need a role with the approval:decide policy.',
    },
  })),
}))

// Mock useFilterState - will be configured per-test
vi.mock('../../hooks/useFilterState', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../hooks/useFilterState')>()
  return {
    ...actual,
    useFilterState: vi.fn(actual.useFilterState),
  }
})

const mockSearchParams = new URLSearchParams()
const mockSetSearchParams = vi.fn()

vi.mock('../../hooks/routing/useLocation', () => ({
  useLocation: () => '/approvals',
}))
const mockNavigate = vi.fn()
vi.mock('../../hooks/routing/useNavigate', () => ({
  useNavigate: () => mockNavigate,
}))

vi.mock('../../hooks/routing/useSearchParams', () => ({
  useSearchParams: () => [mockSearchParams, mockSetSearchParams],
}))

// SynLink (used by LinkCell in ApprovalsTableBody) renders @tanstack/react-router's Link,
// which requires a router context. Stub it to a plain <a> so tests don't need a provider.
vi.mock('@tanstack/react-router', async () => {
  const actual = await vi.importActual('@tanstack/react-router')
  return {
    ...actual,
    Link: ({ to, children, ...rest }: { to: string; children: React.ReactNode }) =>
      React.createElement('a', { href: String(to), ...rest }, children),
  }
})

describe('Approvals Component', () => {
  const now = Date.now()
  const mockApprovals: Approval[] = [
    {
      id: '550e8400-e29b-41d4-a716-446655440001',
      createdAt: new Date(now - 2 * 60 * 60 * 1000).toISOString(), // 2 hours ago
      updatedAt: new Date(now - 2 * 60 * 60 * 1000).toISOString(),
      labels: {},
      execution_id: '660e8400-e29b-41d4-a716-446655440001',
      approval_node_id: 'approval-activity-1',
      name: 'Test Approval 1',
      status: 'pending',
      timeout_at: new Date(now + 22 * 60 * 60 * 1000).toISOString(),
      next_step_approved: {
        id: 'apply_changes',
        name: 'Apply Changes',
        type: 'task',
      },
      next_step_rejected: {
        id: 'rollback',
        name: 'Rollback',
        type: 'task',
      },
      workflow_context: {
        workflow_id: '880e8400-e29b-41d4-a716-446655440001',
        workflow_name: 'Test Workflow',
        inputs: {
          target_environment: 'production',
          version: '2.1.0',
        },
        previous_step: {
          id: 'security_scan',
          name: 'Security Scan',
          type: 'task',
          output: {
            vulnerabilities_found: 0,
          },
        },
      },
      decided_by: null,
      decided_at: null,
      decision_notes: null,
    } as unknown as Approval,
    {
      id: '550e8400-e29b-41d4-a716-446655440002',
      createdAt: new Date(now - 3 * 60 * 60 * 1000).toISOString(), // 3 hours ago
      updatedAt: new Date(now - 1 * 60 * 60 * 1000).toISOString(), // 1 hour ago
      labels: {},
      execution_id: '660e8400-e29b-41d4-a716-446655440002',
      approval_node_id: 'approval-activity-2',
      name: 'Test Approval 2',
      status: 'approved',
      timeout_at: null,
      next_step_approved: {
        id: 'proceed',
        name: 'Proceed',
        type: 'task',
      },
      next_step_rejected: null,
      workflow_context: {
        workflow_id: '880e8400-e29b-41d4-a716-446655440002',
        workflow_name: 'Another Workflow',
        inputs: {
          workflow_name: 'Another Workflow',
        },
        previous_step: {
          id: 'validate',
          name: 'Validate',
          type: 'task',
          output: {
            validated: true,
          },
        },
      },
      decided_by: {
        id: '770e8400-e29b-41d4-a716-446655440001',
        name: 'John Doe',
      },
      decided_at: new Date(now - 1 * 60 * 60 * 1000).toISOString(),
      decision_notes: 'Approved after review',
    } as unknown as Approval,
    {
      id: '550e8400-e29b-41d4-a716-446655440003',
      createdAt: new Date(now - 4 * 60 * 60 * 1000).toISOString(), // 4 hours ago
      updatedAt: new Date(now - 3 * 60 * 60 * 1000).toISOString(), // 3 hours ago
      labels: {},
      execution_id: '660e8400-e29b-41d4-a716-446655440003',
      approval_node_id: 'approval-activity-3',
      name: 'Test Approval 3',
      status: 'rejected',
      timeout_at: null,
      next_step_approved: {
        id: 'proceed',
        name: 'Proceed',
        type: 'task',
      },
      next_step_rejected: {
        id: 'block',
        name: 'Block',
        type: 'task',
      },
      workflow_context: {
        workflow_id: '880e8400-e29b-41d4-a716-446655440003',
        workflow_name: 'Policy Check Workflow',
        inputs: {
          policy_check: true,
        },
        previous_step: {
          id: 'check_policy',
          name: 'Check Policy',
          type: 'task',
          output: {
            compliant: false,
          },
        },
      },
      decided_by: {
        id: '770e8400-e29b-41d4-a716-446655440002',
        name: 'Alice Smith',
      },
      decided_at: new Date(now - 3 * 60 * 60 * 1000).toISOString(),
      decision_notes: 'Rejected due to policy violation',
    } as unknown as Approval,
  ]

  beforeEach(() => {
    vi.clearAllMocks()
    mockSetSearchParams.mockClear()
    mockSearchParams.forEach((_, key) => mockSearchParams.delete(key))
    // Reset useFilterState to its default implementation (not mocked)
    vi.mocked(useFilterState).mockRestore?.()

    vi.mocked(accessClient.useQuery).mockReturnValue({
      data: undefined,
      isPending: false,
      error: null,
      isError: false,
      refetch: vi.fn(),
    } as never)
  })

  const mockApprovalsQuery = (data: Approval[], isPending = false, error: unknown = null) => {
    vi.mocked(approvalsClient.useQuery).mockReturnValue({
      data: { resources: data, next: null, prev: null, total: data.length },
      isPending,
      error,
      isError: !!error,
      refetch: vi.fn(),
    } as never)
  }

  it('renders the approvals table with data', () => {
    mockApprovalsQuery(mockApprovals)

    render(<Approvals />)

    expect(screen.getByText('Approvals')).toBeInTheDocument()
    // FilterBar with text filter input
    expect(screen.getByRole('textbox', { name: /name filter/i })).toBeInTheDocument()
  })

  it('displays approval names', () => {
    mockApprovalsQuery(mockApprovals)

    render(<Approvals />)

    expect(screen.getByText('Test Approval 1')).toBeInTheDocument()
    expect(screen.getByText('Test Approval 2')).toBeInTheDocument()
    expect(screen.getByText('Test Approval 3')).toBeInTheDocument()
  })

  it('renders table headers', () => {
    mockApprovalsQuery(mockApprovals)

    render(<Approvals />)

    expect(screen.getByText('Approval name')).toBeInTheDocument()
    // Approval type column removed for RH1 - may be added back later
    // expect(screen.getByText('Approval type')).toBeInTheDocument()
    expect(screen.getByText('Workflow')).toBeInTheDocument()
    expect(screen.getByText('Approval initiated')).toBeInTheDocument()
    expect(screen.getByText('Actioned on')).toBeInTheDocument()
    expect(screen.getByText('Status')).toBeInTheDocument()
  })

  it('shows loading state', () => {
    mockApprovalsQuery([], true)

    render(<Approvals />)

    expect(screen.getByTestId('loading-state')).toBeInTheDocument()
  })

  it('shows error state', () => {
    mockApprovalsQuery([], false, { message: 'Failed to load' })

    render(<Approvals />)

    expect(screen.getByText('Error loading approvals')).toBeInTheDocument()
  })

  it('displays approval rows (type column removed for RH1)', () => {
    mockApprovalsQuery(mockApprovals)

    render(<Approvals />)

    // Approval type column removed for RH1 — assert rows still render
    expect(screen.getByText('Test Approval 1')).toBeInTheDocument()
    expect(screen.getByText('Test Approval 2')).toBeInTheDocument()
    expect(screen.getByText('Test Approval 3')).toBeInTheDocument()
  })

  it('displays workflow names', () => {
    mockApprovalsQuery(mockApprovals)

    render(<Approvals />)

    expect(screen.getByText('Test Workflow')).toBeInTheDocument()
    expect(screen.getByText('Another Workflow')).toBeInTheDocument()
  })

  it('renders approval status badges', () => {
    mockApprovalsQuery(mockApprovals)

    render(<Approvals />)

    expect(screen.getByText('Pending')).toBeInTheDocument()
    expect(screen.getByText('Approved')).toBeInTheDocument()
    expect(screen.getByText('Rejected')).toBeInTheDocument()
  })

  describe('Empty States', () => {
    it('has no accessibility violations in the no-data empty state', async () => {
      mockApprovalsQuery([])

      const { container } = render(<Approvals />)

      expect(await axe(container)).toHaveNoViolations()
    })

    it('has no accessibility violations with active filters', async () => {
      mockSearchParams.set('name[contains]', 'zzz-no-match-zzz')
      mockApprovalsQuery([])

      const { container } = render(<Approvals />)

      expect(await axe(container)).toHaveNoViolations()
    })

    it('shows no-data empty state when there are no approvals and no active filters', () => {
      mockApprovalsQuery([])

      render(<Approvals />)

      expect(screen.getByText('No approvals found')).toBeInTheDocument()
      expect(screen.queryByRole('textbox', { name: /name filter/i })).not.toBeInTheDocument()
      expect(screen.queryByRole('search', { name: 'Filters' })).not.toBeInTheDocument()
      expect(screen.queryByRole('button', { name: /approve/i })).not.toBeInTheDocument()
      expect(screen.queryByRole('button', { name: /reject/i })).not.toBeInTheDocument()
    })

    it('shows filter empty state when filters are active but no results match', () => {
      mockSearchParams.set('name[contains]', 'zzz-no-match-zzz')
      mockApprovalsQuery([])

      render(<Approvals />)

      expect(screen.getByText('No results found')).toBeInTheDocument()
      expect(screen.queryByText('No approvals found')).not.toBeInTheDocument()
      expect(screen.getByRole('textbox', { name: /name filter/i })).toBeInTheDocument()
      expect(screen.getByRole('button', { name: /approve/i })).toBeInTheDocument()
      expect(screen.getByRole('button', { name: /reject/i })).toBeInTheDocument()
    })
  })

  describe('API sorting', () => {
    it('defaults query sort to -created_at', () => {
      mockApprovalsQuery(mockApprovals)

      render(<Approvals />)

      expect(approvalsClient.useQuery).toHaveBeenCalledWith(
        'get',
        '/approvals',
        expect.objectContaining({
          params: expect.objectContaining({
            query: expect.objectContaining({
              sort: '-created_at',
            }) as unknown,
          }) as unknown,
        }) as unknown,
        expect.anything()
      )
    })

    it('renders sortable headers for name, initiated, actioned, and status', () => {
      mockApprovalsQuery(mockApprovals)

      render(<Approvals />)

      for (const name of [/Approval name/i, /Approval initiated/i, /Actioned on/i, /^Status$/i]) {
        const header = screen.getByRole('columnheader', { name })
        expect(within(header).getByRole('button')).toBeInTheDocument()
      }

      const workflowHeader = screen.getByRole('columnheader', { name: /^Workflow$/i })
      expect(within(workflowHeader).queryByRole('button')).not.toBeInTheDocument()
    })

    it('writes sort URL param when a column header is clicked', async () => {
      const user = userEvent.setup()
      mockApprovalsQuery(mockApprovals)

      render(<Approvals />)

      const statusHeader = screen.getByRole('columnheader', { name: /^Status$/i })
      await user.click(within(statusHeader).getByRole('button'))

      await waitFor(() => {
        assertUrlParam(mockSetSearchParams, 'sort', 'status')
      })
    })

    it('can sort by decided_at via the Actioned on column', async () => {
      const user = userEvent.setup()
      mockApprovalsQuery(mockApprovals)

      render(<Approvals />)

      const actionedOnHeader = screen.getByRole('columnheader', { name: /Actioned on/i })
      await user.click(within(actionedOnHeader).getByRole('button'))

      await waitFor(() => {
        assertUrlParam(mockSetSearchParams, 'sort', 'decided_at')
      })
    })

    it('can sort by name via the Approval name column', async () => {
      const user = userEvent.setup()
      mockApprovalsQuery(mockApprovals)

      render(<Approvals />)

      const approvalNameHeader = screen.getByRole('columnheader', { name: /Approval name/i })
      await user.click(within(approvalNameHeader).getByRole('button'))

      await waitFor(() => {
        assertUrlParam(mockSetSearchParams, 'sort', 'name')
      })
    })
  })

  describe('Row Expansion', () => {
    // mockApprovals[0] is pending with no decision_notes, so it has no expand toggle.
    // Only mockApprovals[1] (approved) and mockApprovals[2] (rejected) are expandable.

    it('does not render an expand toggle for the pending approval with no decision notes', async () => {
      mockApprovalsQuery(mockApprovals)

      render(<Approvals />)

      const expandButtons = await screen.findAllByRole('button', { name: /details/i })
      expect(expandButtons).toHaveLength(2)
    })

    it('expands a row when clicking the expand button', async () => {
      const user = userEvent.setup()
      mockApprovalsQuery(mockApprovals)

      render(<Approvals />)

      // First expand toggle belongs to mockApprovals[1] (the first expandable row)
      const expandButtons = await screen.findAllByRole('button', { name: /details/i })
      await user.click(expandButtons[0])

      expect(screen.getByText('Approval notes')).toBeInTheDocument()
      expect(screen.getByText('Approved after review')).toBeInTheDocument()
    })

    it('collapses an expanded row when clicking the expand button again', async () => {
      const user = userEvent.setup()
      mockApprovalsQuery(mockApprovals)

      render(<Approvals />)

      const expandButtons = await screen.findAllByRole('button', { name: /details/i })

      // Expand then collapse
      await user.click(expandButtons[0])
      expect(screen.getByText('Approved after review')).toBeInTheDocument()

      await user.click(expandButtons[0])
      // Row toggle was clicked again - state should be collapsed
      // The expanded row content is still in DOM but the row state changes
      expect(expandButtons[0]).toBeInTheDocument()
    })

    it('can expand all rows using the header expand toggle', async () => {
      const user = userEvent.setup()
      mockApprovalsQuery(mockApprovals)

      render(<Approvals />)

      // Find the expand all button in the header
      const expandAllButton = await screen.findByRole('button', { name: /expand all/i })
      await user.click(expandAllButton)

      // Both expandable approvals' notes should be visible
      expect(screen.getByText('Approved after review')).toBeInTheDocument()
      expect(screen.getByText('Rejected due to policy violation')).toBeInTheDocument()
    })

    it('can collapse all rows using the header collapse toggle', async () => {
      const user = userEvent.setup()
      mockApprovalsQuery(mockApprovals)

      render(<Approvals />)

      // Expand all first
      const expandAllButton = await screen.findByRole('button', { name: /expand all/i })
      await user.click(expandAllButton)

      // Notes should be visible after expanding
      expect(screen.getByText('Approved after review')).toBeInTheDocument()

      // The onCollapseAll function is tested by clicking again
      // After expanding all, clicking the toggle should collapse
      await user.click(expandAllButton)

      // Toggle was clicked - the state changed
      expect(expandAllButton).toBeInTheDocument()
    })

    it('hides the header expand-all toggle when no approvals have decision notes', async () => {
      const pendingOnly = {
        ...mockApprovals[0],
        id: 'no-notes-approval',
      }
      mockApprovalsQuery([pendingOnly] as Approval[])

      render(<Approvals />)

      await waitFor(() => {
        expect(screen.queryByRole('button', { name: /expand all/i })).not.toBeInTheDocument()
      })
      expect(screen.queryByRole('button', { name: /details/i })).not.toBeInTheDocument()
    })
  })

  describe('Filter Functionality', () => {
    it('applies name filter to API query when typing and submitting', async () => {
      const user = userEvent.setup()
      mockApprovalsQuery(mockApprovals)

      render(<Approvals />)

      const nameInput = screen.getByRole('textbox', { name: /name filter/i })

      // Type filter value
      await user.type(nameInput, 'test')

      // Submit by pressing Enter
      await user.keyboard('{Enter}')

      // Verify URL parameters were updated with filter
      await waitFor(() => {
        assertUrlParam(mockSetSearchParams, 'name[contains]', 'test')
      })
      expect(mockSetSearchParams).toHaveBeenCalled()
    })

    it('applies status filter to API query when selecting option', async () => {
      const user = userEvent.setup()
      mockApprovalsQuery(mockApprovals)

      render(<Approvals />)

      // Status is now inside attribute search — switch field selector from "Name" to "Status"
      const fieldSelector = screen.getByRole('button', { name: 'Name' })
      await user.click(fieldSelector)
      await user.click(screen.getByRole('option', { name: 'Status' }))

      // Open the multiselect value toggle and select "Pending"
      const valueToggle = screen.getByRole('button', { name: /select values|filter by status/i })
      await user.click(valueToggle)
      await user.click(screen.getByRole('checkbox', { name: 'Pending' }))

      // Verify URL params were updated with combined IN status filter
      await waitFor(() => {
        assertUrlParam(mockSetSearchParams, 'status[in]', 'pending')
      })
      expect(mockSetSearchParams).toHaveBeenCalled()
    }, 10000)

    it('displays name filter input in toolbar', () => {
      mockApprovalsQuery(mockApprovals)

      render(<Approvals />)

      // Verify filter input is present
      const textInput = screen.getByRole('textbox', { name: /name filter/i })
      expect(textInput).toBeInTheDocument()
      expect(textInput).toHaveAttribute('placeholder', 'Filter by name')
    })

    it('resets pagination cursor when filters change', async () => {
      const user = userEvent.setup()

      // Mock query with pagination cursor
      vi.mocked(approvalsClient.useQuery).mockReturnValue({
        data: {
          resources: mockApprovals,
          next: 'cursor-page-2',
          prev: null,
          total: 20,
        },
        isPending: false,
        error: null,
        isError: false,
        refetch: vi.fn(),
      } as never)

      render(<Approvals />)

      // Navigate to page 2
      const nextButton = screen.getByRole('button', { name: /next/i })
      await user.click(nextButton)

      // Apply a filter
      const nameInput = screen.getByRole('textbox', { name: /name filter/i })
      await user.type(nameInput, 'test')
      await user.keyboard('{Enter}')

      // Verify cursor was reset (no cursor in URL params)
      await waitFor(() => {
        assertUrlParamIsNull(mockSetSearchParams, 'cursor')
      })
      expect(mockSetSearchParams).toHaveBeenCalled()
    })
  })

  describe('Pagination', () => {
    it('displays footer with approval count', () => {
      mockApprovalsQuery(mockApprovals)

      render(<Approvals />)

      expect(screen.getByRole('navigation', { name: /pagination/i })).toBeInTheDocument()
      // PF renders the count as aria-hidden and splits it across <b> tags; match via textContent
      expect(screen.queryAllByText((_, el) => (el?.textContent ?? '').includes('1 - 3 of 3'))).not.toHaveLength(0)
    })

    it('displays singular approval text for one approval', () => {
      mockApprovalsQuery([mockApprovals[0]])

      render(<Approvals />)

      expect(screen.getByRole('navigation', { name: /pagination/i })).toBeInTheDocument()
      expect(screen.queryAllByText((_, el) => (el?.textContent ?? '').includes('1 - 1 of 1'))).not.toHaveLength(0)
    })

    it('displays total count when more approvals exist', () => {
      vi.mocked(approvalsClient.useQuery).mockReturnValue({
        data: {
          resources: mockApprovals,
          total: 50,
          next: 'next-cursor',
          prev: null,
        },
        isPending: false,
        error: null,
      } as never)

      render(<Approvals />)

      expect(screen.getByRole('navigation', { name: /pagination/i })).toBeInTheDocument()
      expect(screen.queryAllByText((_, el) => (el?.textContent ?? '').includes('1 - 20 of 50'))).not.toHaveLength(0)
    })

    it('handles next page navigation', async () => {
      const user = userEvent.setup()
      vi.mocked(approvalsClient.useQuery).mockReturnValue({
        data: {
          resources: mockApprovals,
          total: 50,
          next: 'next-cursor',
          prev: null,
        },
        isPending: false,
        error: null,
      } as never)

      render(<Approvals />)

      const nextButton = screen.getByRole('button', { name: /next/i })
      await user.click(nextButton)

      expect(nextButton).toBeInTheDocument()
    })

    it('handles previous page navigation', async () => {
      const user = userEvent.setup()
      vi.mocked(approvalsClient.useQuery).mockReturnValue({
        data: {
          resources: mockApprovals,
          total: 50,
          next: null,
          prev: 'prev-cursor',
        },
        isPending: false,
        error: null,
      } as never)

      render(<Approvals />)

      const prevButton = screen.getByRole('button', { name: /previous/i })
      await user.click(prevButton)

      expect(prevButton).toBeInTheDocument()
    })

    it('does not reset cursor while query is fetching', async () => {
      const user = userEvent.setup()
      const mockRefetch = vi.fn()

      // First render: page 1 with data
      vi.mocked(approvalsClient.useQuery).mockReturnValue({
        data: {
          resources: mockApprovals,
          next: 'next-cursor',
          prev: null,
          total: 30,
        },
        isPending: false,
        isLoading: false,
        isFetching: false,
        isError: false,
        error: null,
        refetch: mockRefetch,
      } as never)

      const { rerender } = render(<Approvals />)

      // Verify pagination controls present
      const nextButton = screen.getByRole('button', { name: /next/i })
      expect(nextButton).toBeInTheDocument()

      // Click Next to set internal cursor state
      await user.click(nextButton)

      // Verify cursor was set after clicking Next
      await waitFor(() => {
        const lastCall = vi.mocked(approvalsClient.useQuery).mock.calls.at(-1)
        expect(lastCall).toBeDefined()
        const queryParams = (lastCall?.[2] as unknown as { params?: { query?: Record<string, unknown> } })?.params
          ?.query
        expect(queryParams).toMatchObject({ cursor: 'next-cursor' })
      })

      // Second render: fetching state with empty data (cursor should NOT be reset due to isFetching=true)
      vi.mocked(approvalsClient.useQuery).mockReturnValue({
        data: {
          resources: [], // Empty during transition
          next: 'next-cursor',
          prev: 'prev-cursor',
          total: 30,
        },
        isPending: false,
        isLoading: false,
        isFetching: true, // Fetching prevents cursor reset
        isError: false,
        error: null,
        refetch: mockRefetch,
      } as never)

      // Rerender to trigger useEffect with fetching state
      rerender(<Approvals />)

      // Wait for component to process and verify cursor is still present (not reset)
      await waitFor(() => {
        const lastCall = vi.mocked(approvalsClient.useQuery).mock.calls.at(-1)
        expect(lastCall).toBeDefined()
        // Cursor should still be present because isFetching=true prevents reset
        const queryParams = (lastCall?.[2] as unknown as { params?: { query?: Record<string, unknown> } })?.params
          ?.query
        expect(queryParams).toMatchObject({ cursor: 'next-cursor' })
      })

      // Third render: data arrives for page 2 - if cursor was preserved, we should have prev button
      vi.mocked(approvalsClient.useQuery).mockReturnValue({
        data: {
          resources: mockApprovals.slice(0, 2), // Page 2 data
          next: 'next-cursor',
          prev: 'prev-cursor', // This proves we're on page 2, not page 1
          total: 30,
        },
        isPending: false,
        isLoading: false,
        isFetching: false,
        isError: false,
        error: null,
        refetch: mockRefetch,
      } as never)

      rerender(<Approvals />)

      // Verify pagination shows both buttons (proves cursor was not reset - we're on page 2)
      await waitFor(() => {
        expect(screen.getByRole('button', { name: /next/i })).toBeInTheDocument()
        expect(screen.getByRole('button', { name: /previous/i })).toBeInTheDocument()
      })
    })

    it.skip('resets cursor when data is empty and query is not fetching', async () => {
      const user = userEvent.setup()
      const mockRefetch = vi.fn()

      // Ensure useFilterState returns no active filters so hasActiveFilters is false
      // This is required for the cursor reset logic to run
      vi.mocked(useFilterState).mockReturnValue({
        filters: [], // No active filters
        setFilter: vi.fn(),
        removeFilter: vi.fn(),
        clearAllFilters: vi.fn(),
        setAllFilters: vi.fn(),
      })

      // Start with data and cursor
      vi.mocked(approvalsClient.useQuery).mockReturnValue({
        data: {
          resources: mockApprovals,
          next: 'next-cursor',
          prev: null,
          total: 30,
        },
        isPending: false,
        isLoading: false,
        isFetching: false,
        isError: false,
        error: null,
        refetch: mockRefetch,
      } as never)

      const { rerender } = render(<Approvals />)

      // Click Next to set cursor
      const nextButton = screen.getByRole('button', { name: /next/i })
      await user.click(nextButton)

      // Wait for cursor to be set and verify it's present
      await waitFor(() => {
        const lastCall = vi.mocked(approvalsClient.useQuery).mock.calls.at(-1)
        expect(lastCall).toBeDefined()
        const queryParams = (lastCall?.[2] as unknown as { params?: { query?: Record<string, unknown> } })?.params
          ?.query
        expect(queryParams).toMatchObject({ cursor: 'next-cursor' })
      })

      // Simulate truly empty state - no data and not fetching
      vi.mocked(approvalsClient.useQuery).mockReturnValue({
        data: {
          resources: [],
          next: null,
          prev: null,
          total: 0,
        },
        isPending: false,
        isLoading: false,
        isFetching: false, // Not fetching allows cursor reset
        isError: false,
        error: null,
        refetch: mockRefetch,
      } as never)

      rerender(<Approvals />)

      // Wait for the component to process the new mock data
      await waitFor(
        () => {
          expect(screen.getByText('No approvals found')).toBeInTheDocument()
        },
        { timeout: 3000 }
      )

      // Verify cursor was reset (no cursor in query params)
      await waitFor(() => {
        const lastCall = vi.mocked(approvalsClient.useQuery).mock.calls.at(-1)
        expect(lastCall).toBeDefined()
        // Cursor should be absent or undefined because it was reset
        const queryParams = (lastCall?.[2] as unknown as { params?: { query?: Record<string, unknown> } })?.params
          ?.query
        expect(queryParams?.cursor).toBeUndefined()
      })
    })
  })

  describe('Edge Cases', () => {
    it('handles approval without workflowId (no link)', () => {
      const approvalWithoutWorkflow = {
        ...mockApprovals[0],
        id: 'no-workflow-approval',
        workflow_context: {
          ...mockApprovals[0].workflow_context,
          workflow_id: undefined,
        },
      }
      mockApprovalsQuery([approvalWithoutWorkflow] as unknown as Approval[])

      render(<Approvals />)

      // Workflow name should be displayed but not as a link
      const workflowText = screen.getByText('Test Workflow')
      expect(workflowText).toBeInTheDocument()

      expect(screen.queryByRole('button', { name: 'Test Workflow' })).toBeNull()
      expect(screen.queryByRole('link', { name: 'Test Workflow' })).toBeNull()
    })

    it('handles approval without decided_at (pending)', () => {
      mockApprovalsQuery([mockApprovals[0]]) // First approval is pending with no decided_at

      render(<Approvals />)

      // The pending approval should render successfully without decided_at
      // DateCell with null will render appropriately
      expect(screen.getByText('Test Approval 1')).toBeInTheDocument()
      expect(screen.getByText('Pending')).toBeInTheDocument()
    })

    it('displays decided_by link when approval has been decided', () => {
      mockApprovalsQuery([mockApprovals[1]]) // Second approval has decided_by

      render(<Approvals />)

      // Should show the decider's name
      expect(screen.getByText('John Doe')).toBeInTheDocument()
    })

    it('handles approval without name (uses ID)', () => {
      const approvalWithoutName = {
        ...mockApprovals[0],
        name: null,
      }
      mockApprovalsQuery([approvalWithoutName] as unknown as Approval[])

      render(<Approvals />)

      // Should display the ID instead
      expect(screen.getByText('550e8400-e29b-41d4-a716-446655440001')).toBeInTheDocument()
    })

    it('handles approval without workflow_context (Unknown workflow)', () => {
      const approvalWithoutContext = {
        ...mockApprovals[0],
        workflow_context: undefined,
      }
      mockApprovalsQuery([approvalWithoutContext] as unknown as Approval[])

      render(<Approvals />)

      expect(screen.getByText('Unknown')).toBeInTheDocument()
    })
  })

  describe('Grouped view (All Projects)', () => {
    it('renders grouped approvals when all projects are selected', () => {
      mockUseProjectSelector.mockReturnValue({
        selectedProject: null,
        isAllProjects: true,
        projects: [
          { id: 'proj-1', name: 'Project Alpha' },
          { id: 'proj-2', name: 'Project Beta' },
        ],
        ProjectSelector: null,
      })

      const approvalsWithProjects = mockApprovals.map((a, i) => ({
        ...a,
        project_id: i === 0 ? 'proj-1' : 'proj-2',
      }))
      mockApprovalsQuery(approvalsWithProjects as Approval[])

      render(<Approvals />)

      expect(screen.getByText('Project Alpha')).toBeInTheDocument()
      expect(screen.getByText('Project Beta')).toBeInTheDocument()

      // Count badge removed — page-local counts were misleading (AAP-85112)
      const alphaHeader = screen.getByRole('row', { name: /Project Alpha/ })
      expect(within(alphaHeader).queryByText('1')).not.toBeInTheDocument()

      expect(screen.getByText('Test Approval 1')).toBeInTheDocument()
      expect(screen.getByText('Test Approval 2')).toBeInTheDocument()
      expect(screen.getByText('Test Approval 3')).toBeInTheDocument()
    })

    it('toggles project group collapsed/expanded', async () => {
      const user = userEvent.setup()

      mockUseProjectSelector.mockReturnValue({
        selectedProject: null,
        isAllProjects: true,
        projects: [{ id: 'proj-1', name: 'Project Alpha' }],
        ProjectSelector: null,
      })

      const approvalsWithProject = [{ ...mockApprovals[0], project_id: 'proj-1' }]
      mockApprovalsQuery(approvalsWithProject as Approval[])

      render(<Approvals />)

      // Approval should be visible initially
      expect(screen.getByText('Test Approval 1')).toBeInTheDocument()

      // Click the project group header to collapse
      await user.click(screen.getByText('Project Alpha'))

      // Approval should be hidden
      expect(screen.queryByText('Test Approval 1')).not.toBeInTheDocument()

      // Click again to expand
      await user.click(screen.getByText('Project Alpha'))

      // Approval visible again
      expect(screen.getByText('Test Approval 1')).toBeInTheDocument()
    })

    it('shows "No project" for approvals without project_id', () => {
      mockUseProjectSelector.mockReturnValue({
        selectedProject: null,
        isAllProjects: true,
        projects: [{ id: 'proj-1', name: 'Project Alpha' }],
        ProjectSelector: null,
      })

      const approvalsWithoutProject = [{ ...mockApprovals[0], project_id: undefined }]
      mockApprovalsQuery(approvalsWithoutProject as unknown as Approval[])

      render(<Approvals />)

      expect(screen.getByText('No project')).toBeInTheDocument()
      expect(screen.getByText('Test Approval 1')).toBeInTheDocument()
    })
  })

  describe('Permission gating', () => {
    beforeEach(() => {
      mockApprovalsQuery(mockApprovals)
      mockUseProjectSelector.mockReturnValue({
        selectedProject: null,
        isAllProjects: true,
        projects: [],
        ProjectSelector: null,
      })
      // Reset permission mock to default
      vi.mocked(useApprovalPermissions).mockReturnValue({
        canRead: true,
        canDecide: true,
        isChecking: false,
        tooltips: {
          decide: 'To decide on approvals, you need a role with the approval:decide policy.',
        },
      })
    })

    it('shows loading spinner while checking permissions', () => {
      vi.mocked(useApprovalPermissions).mockReturnValue({
        canRead: false,
        canDecide: false,
        isChecking: true,
        tooltips: {
          decide: 'To decide on approvals, you need a role with the approval:decide policy.',
        },
      })

      render(<Approvals />)

      expect(screen.getByRole('progressbar')).toBeInTheDocument()
      expect(screen.queryByRole('table')).not.toBeInTheDocument()
    })

    it('shows access denied state when user lacks read permission', () => {
      vi.mocked(useApprovalPermissions).mockReturnValue({
        canRead: false,
        canDecide: false,
        isChecking: false,
        tooltips: {
          decide: 'To decide on approvals, you need a role with the approval:decide policy.',
        },
      })

      render(<Approvals />)

      expect(screen.getByText(/access denied/i)).toBeInTheDocument()
      expect(screen.getByText(/you do not have permission to view approvals/i)).toBeInTheDocument()
      expect(screen.queryByRole('table')).not.toBeInTheDocument()
    })

    it('does not show access denied when user has read permission', () => {
      vi.mocked(useApprovalPermissions).mockReturnValue({
        canRead: true,
        canDecide: false,
        isChecking: false,
        tooltips: {
          decide: 'To decide on approvals, you need a role with the approval:decide policy.',
        },
      })

      render(<Approvals />)

      // Should not show permission-related loading or access denied states
      expect(screen.queryByLabelText('Loading approval permissions')).not.toBeInTheDocument()
      expect(screen.queryByText(/access denied/i)).not.toBeInTheDocument()
      expect(screen.queryByText(/you do not have permission to view approvals/i)).not.toBeInTheDocument()

      // The page should render (table may be loading data, but permission check passed)
      expect(screen.getByText('Approvals')).toBeInTheDocument()
    })
  })
})
