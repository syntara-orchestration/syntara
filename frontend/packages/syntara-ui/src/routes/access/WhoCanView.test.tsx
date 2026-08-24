import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type React from 'react'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { axe } from 'vitest-axe'

import { accessClient, accessFetchClient, dynamicFetchClient } from './accessClient'
import { ACTION_HELP, PROJECT_HELP, RESOURCE_ID_HELP, RESOURCE_TYPE_HELP } from './accessControlFieldHelpText'
import type { ResourceActionMap } from './canIUtils'
import { useAllProjects, useSelectableProjects } from './useAllProjects'
import { WhoCanView } from './WhoCanView'

const { mockMutate } = vi.hoisted(() => ({
  mockMutate: vi.fn<(...args: unknown[]) => void>(),
}))

vi.mock('../../client', () => ({
  authMiddleware: { onRequest: vi.fn() },
  interfaceTagMiddleware: { onRequest: vi.fn() },
}))

vi.mock('./useAllProjects', () => ({
  useAllProjects: vi.fn(),
  useSelectableProjects: vi.fn(),
}))

vi.mock('./accessClient', () => ({
  accessClient: {
    useQuery: vi.fn(),
    useMutation: vi.fn(),
  },
  accessFetchClient: {
    GET: vi.fn(),
    POST: vi.fn(),
  },
  dynamicFetchClient: {
    GET: vi.fn(),
  },
}))

const sampleResourceActions: ResourceActionMap = {
  resourceTypes: ['project', 'workflow'],
  actionsByResource: new Map([
    ['project', ['read']],
    ['workflow', ['read', 'write']],
  ]),
}

const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
const wrapper = ({ children }: { children: React.ReactNode }) => (
  <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
)

function mockMutationState(overrides: Record<string, unknown>) {
  vi.mocked(accessClient.useMutation).mockReturnValue({
    mutate: mockMutate,
    mutateAsync: vi.fn(),
    isPending: false,
    isIdle: false,
    isError: false,
    isSuccess: false,
    data: undefined,
    error: null,
    reset: vi.fn(),
    status: 'idle',
    failureCount: 0,
    failureReason: null,
    context: undefined,
    submittedAt: 0,
    variables: undefined,
    isPaused: false,
    ...overrides,
  } as never)
}

describe('WhoCanView', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    queryClient.clear()
    vi.mocked(accessClient.useQuery).mockReturnValue({
      data: { resources: [], next: null },
      isPending: false,
      error: null,
    } as never)
    vi.mocked(accessFetchClient.GET).mockResolvedValue({ data: { resources: [] } } as never)
    vi.mocked(dynamicFetchClient.GET).mockResolvedValue({ data: { resources: [] } } as never)
    const projectsMockValue = {
      projects: [
        {
          id: 'proj-1',
          name: 'default',
          description: undefined,
          labels: {},
          is_default: false,
          created_at: '2024-01-01T00:00:00Z',
          updated_at: '2024-01-01T00:00:00Z',
        },
      ],
      isLoading: false,
      error: null,
      refetch: vi.fn(),
    }
    vi.mocked(useAllProjects).mockReturnValue(projectsMockValue)
    vi.mocked(useSelectableProjects).mockReturnValue(projectsMockValue)
    // Reset to default idle state
    vi.mocked(accessClient.useMutation).mockReturnValue({
      mutate: mockMutate,
      mutateAsync: vi.fn(),
      isPending: false,
      isIdle: true,
      isError: false,
      isSuccess: false,
      data: undefined,
      error: null,
      reset: vi.fn(),
      status: 'idle',
      failureCount: 0,
      failureReason: null,
      context: undefined,
      submittedAt: 0,
      variables: undefined,
      isPaused: false,
    } as never)
  })

  it('renders empty state initially', () => {
    render(<WhoCanView {...sampleResourceActions} />, { wrapper })

    expect(screen.getByText('Find who has access')).toBeInTheDocument()
    expect(screen.getByText('Enter an action and resource type to see which users can perform it.')).toBeInTheDocument()
  })

  it('renders form fields', () => {
    render(<WhoCanView {...sampleResourceActions} />, { wrapper })

    expect(screen.getByText('Resource type')).toBeInTheDocument()
    expect(screen.getByText('Action')).toBeInTheDocument()
    expect(screen.getByText('Resource ID')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Find Users' })).toBeInTheDocument()
  })

  it('disables Find Users button when form is incomplete', () => {
    render(<WhoCanView {...sampleResourceActions} />, { wrapper })

    expect(screen.getByRole('button', { name: 'Find Users' })).toBeDisabled()
  })

  it('populates action options after resource type is chosen', async () => {
    const user = userEvent.setup()
    render(<WhoCanView {...sampleResourceActions} />, { wrapper })

    // Select resource type via typeahead
    await user.click(screen.getByPlaceholderText('Select a resource type'))
    await user.click(screen.getByRole('option', { name: /workflow/i }))

    // Action typeahead should now have options
    await user.click(screen.getByPlaceholderText('Select an action'))
    expect(screen.getByRole('option', { name: /read/i })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: /write/i })).toBeInTheDocument()
  })

  it('shows users table on successful response', () => {
    mockMutationState({
      isSuccess: true,
      data: {
        resources: [
          { id: 'u1', username: 'alice' },
          { id: 'u2', username: 'bob' },
        ],
      },
    })

    render(<WhoCanView {...sampleResourceActions} />, { wrapper })

    expect(screen.getByText('alice')).toBeInTheDocument()
    expect(screen.getByText('bob')).toBeInTheDocument()
    expect(screen.getByRole('grid', { name: 'Users with access' })).toHaveClass('pf-m-striped')
  })

  it('links usernames to user detail pages', () => {
    mockMutationState({
      isSuccess: true,
      data: {
        resources: [
          { id: 'u1', username: 'alice' },
          { id: 'u2', username: 'bob' },
        ],
      },
    })

    render(<WhoCanView {...sampleResourceActions} />, { wrapper })

    expect(screen.getByRole('link', { name: 'alice' })).toHaveAttribute(
      'href',
      '/system-administration/access-management/users/u1'
    )
    expect(screen.getByRole('link', { name: 'bob' })).toHaveAttribute(
      'href',
      '/system-administration/access-management/users/u2'
    )
  })

  it('shows warning when no users found', () => {
    mockMutationState({
      isSuccess: true,
      data: { resources: [] },
    })

    render(<WhoCanView {...sampleResourceActions} />, { wrapper })

    // The plain alert renders as a heading, not role="alert"
    expect(screen.getByRole('heading', { name: /No users can perform/ })).toBeInTheDocument()
  })

  it('shows singular "user" when exactly one user found', () => {
    mockMutationState({
      isSuccess: true,
      data: { resources: [{ id: 'u1', username: 'alice' }] },
    })

    render(<WhoCanView {...sampleResourceActions} />, { wrapper })

    expect(screen.getByText('alice')).toBeInTheDocument()
  })

  it('shows error state when API call fails', () => {
    mockMutationState({
      isError: true,
      error: new Error('Server error'),
    })

    render(<WhoCanView {...sampleResourceActions} />, { wrapper })

    expect(screen.getByText('Query failed')).toBeInTheDocument()
  })

  it('shows spinner while searching', () => {
    mockMutationState({ isPending: true, isIdle: false })

    render(<WhoCanView {...sampleResourceActions} />, { wrapper })

    expect(screen.getByRole('progressbar', { name: 'Finding users' })).toBeInTheDocument()
  })

  it('calls mutate with correct params on submit', async () => {
    const user = userEvent.setup()
    render(<WhoCanView {...sampleResourceActions} />, { wrapper })

    // Select resource type via typeahead
    await user.click(screen.getByPlaceholderText('Select a resource type'))
    await user.click(screen.getByRole('option', { name: /workflow/i }))

    // Select action via typeahead
    await user.click(screen.getByPlaceholderText('Select an action'))
    await user.click(screen.getByRole('option', { name: /^read$/i }))

    await user.click(screen.getByRole('button', { name: 'Find Users' }))

    await waitFor(() => {
      expect(mockMutate).toHaveBeenCalledWith(
        expect.objectContaining({
          // eslint-disable-next-line @typescript-eslint/no-unsafe-assignment
          body: expect.objectContaining({
            action: 'read',
            resource_type: 'workflow',
          }),
        })
      )
    })
  })

  it('has no accessibility violations', async () => {
    const { container } = render(<WhoCanView {...sampleResourceActions} />, { wrapper })
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('has no accessibility violations when results are shown', async () => {
    mockMutationState({
      isSuccess: true,
      data: {
        resources: [
          { id: 'u1', username: 'alice' },
          { id: 'u2', username: 'bob' },
        ],
      },
    })

    const { container } = render(<WhoCanView {...sampleResourceActions} />, { wrapper })
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  describe('Results display', () => {
    it('shows user count in footer', () => {
      mockMutationState({
        isSuccess: true,
        data: {
          resources: [
            { id: 'u1', username: 'alice' },
            { id: 'u2', username: 'bob' },
          ],
        },
      })

      render(<WhoCanView {...sampleResourceActions} />, { wrapper })

      expect(screen.getByText('2 users')).toBeInTheDocument()
      expect(within(screen.getByTestId('scrollable-table-container-root')).getByText('2 users')).toBeInTheDocument()
    })

    it('shows singular "user" for one result', () => {
      mockMutationState({
        isSuccess: true,
        data: { resources: [{ id: 'u1', username: 'alice' }] },
      })

      render(<WhoCanView {...sampleResourceActions} />, { wrapper })

      expect(screen.getByText('1 user')).toBeInTheDocument()
    })

    it('includes project name in alert when project is selected', async () => {
      const user = userEvent.setup()
      mockMutationState({
        isSuccess: true,
        data: { resources: [{ id: 'u1', username: 'alice' }] },
      })

      render(<WhoCanView {...sampleResourceActions} />, { wrapper })

      // Select a project via PF Select
      await user.click(screen.getByRole('button', { name: 'Project' }))
      await user.click(screen.getByRole('option', { name: 'default' }))

      expect(screen.getByRole('heading', { name: /in "default" project/ })).toBeInTheDocument()
    })
  })

  describe('Pagination', () => {
    it('shows pagination buttons when next cursor is present', () => {
      mockMutationState({
        isSuccess: true,
        data: {
          resources: [{ id: 'u1', username: 'alice' }],
          next: 'cursor-abc',
        },
      })

      render(<WhoCanView {...sampleResourceActions} />, { wrapper })

      expect(screen.getByRole('button', { name: 'Next page' })).toBeEnabled()
      expect(screen.getByRole('button', { name: 'Previous page' })).toBeDisabled()
      expect(
        within(screen.getByTestId('scrollable-table-container-root')).getByRole('button', { name: 'Next page' })
      ).toBeInTheDocument()
    })

    it('does not show pagination buttons when no cursor', () => {
      mockMutationState({
        isSuccess: true,
        data: { resources: [{ id: 'u1', username: 'alice' }] },
      })

      render(<WhoCanView {...sampleResourceActions} />, { wrapper })

      expect(screen.queryByRole('button', { name: 'Next page' })).not.toBeInTheDocument()
    })

    it('calls mutate with cursor when Next is clicked', async () => {
      const user = userEvent.setup()
      mockMutationState({
        isSuccess: true,
        data: {
          resources: [{ id: 'u1', username: 'alice' }],
          next: 'cursor-abc',
        },
      })

      render(<WhoCanView {...sampleResourceActions} />, { wrapper })

      // First submit the form to set lastFormData
      await user.click(screen.getByPlaceholderText('Select a resource type'))
      await user.click(screen.getByRole('option', { name: /workflow/i }))
      await user.click(screen.getByPlaceholderText('Select an action'))
      await user.click(screen.getByRole('option', { name: /^read$/i }))
      await user.click(screen.getByRole('button', { name: 'Find Users' }))

      await waitFor(() => {
        expect(mockMutate).toHaveBeenCalled()
      })

      // Now click Next
      await user.click(screen.getByRole('button', { name: 'Next page' }))

      await waitFor(() => {
        const lastCall = mockMutate.mock.calls.at(-1) as unknown[]
        expect(lastCall[0]).toEqual(
          expect.objectContaining({
            // eslint-disable-next-line @typescript-eslint/no-unsafe-assignment
            body: expect.objectContaining({ cursor: 'cursor-abc' }),
          })
        )
      })
    })
  })

  describe('field help popovers', () => {
    it('shows resource type, action, project, and resource id help on click', async () => {
      const user = userEvent.setup()
      render(<WhoCanView {...sampleResourceActions} />, { wrapper })

      await user.click(screen.getByRole('button', { name: 'More info for Resource type' }))
      expect(screen.getByText(RESOURCE_TYPE_HELP)).toBeInTheDocument()

      await user.keyboard('{Escape}')
      await user.click(screen.getByRole('button', { name: 'More info for Action' }))
      expect(screen.getByText(ACTION_HELP)).toBeInTheDocument()

      await user.keyboard('{Escape}')
      await user.click(screen.getByRole('button', { name: 'More info for Project' }))
      expect(screen.getByText(PROJECT_HELP)).toBeInTheDocument()

      await user.keyboard('{Escape}')
      await user.click(screen.getByRole('button', { name: 'More info for Resource ID' }))
      expect(screen.getByText(RESOURCE_ID_HELP)).toBeInTheDocument()
    })
  })
})
