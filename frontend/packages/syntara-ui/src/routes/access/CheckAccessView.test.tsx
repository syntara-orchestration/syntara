import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type React from 'react'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { axe } from 'vitest-axe'

import { mockAuthMiddleware } from '../../test/mockAuthMiddleware'

import { accessClient, accessFetchClient, dynamicFetchClient } from './accessClient'
import { ACTION_HELP, PROJECT_HELP, RESOURCE_ID_HELP, RESOURCE_TYPE_HELP } from './accessControlFieldHelpText'
import type { ResourceActionMap } from './canIUtils'
import { CheckAccessView } from './CheckAccessView'
import { useAllProjects, useSelectableProjects } from './useAllProjects'

const { mockMutate } = vi.hoisted(() => ({
  mockMutate: vi.fn<(...args: unknown[]) => void>(),
}))

vi.mock('../../client', () => ({
  authMiddleware: mockAuthMiddleware,
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

const sampleCheckAccessRequest = { body: { action: 'read', resource_type: 'project', resource_project: 'default' } }

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

/** Helper to fill the form with resource type "project" and action "read" */
async function fillForm(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByPlaceholderText('Select a resource type'))
  await user.click(screen.getByRole('option', { name: /^project$/i }))
  // project only has 'read', auto-selected via cascade effect
  await waitFor(() => {
    const actionInput = screen.getByPlaceholderText('Select an action')
    expect(actionInput).toHaveValue('read')
  })
}

describe('CheckAccessView', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    queryClient.clear()
    vi.mocked(accessFetchClient.GET).mockResolvedValue({ data: { resources: [] } } as never)
    vi.mocked(dynamicFetchClient.GET).mockResolvedValue({
      data: { resources: [] },
      error: undefined,
      response: new Response(),
    })
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

  it('renders the empty state initially', () => {
    render(<CheckAccessView {...sampleResourceActions} />, { wrapper })

    expect(screen.getByText('Check access permissions')).toBeInTheDocument()
    expect(
      screen.getByText('Select a resource type and action, then click Check access to verify your permissions.')
    ).toBeInTheDocument()
  })

  it('renders form fields', () => {
    render(<CheckAccessView {...sampleResourceActions} />, { wrapper })

    expect(screen.getByText('Resource type')).toBeInTheDocument()
    expect(screen.getByText('Action')).toBeInTheDocument()
    expect(screen.getByText('Resource ID')).toBeInTheDocument()
    expect(screen.getByText('Project')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Check access' })).toBeInTheDocument()
  })

  it('disables Check access button when form is incomplete', () => {
    render(<CheckAccessView {...sampleResourceActions} />, { wrapper })

    expect(screen.getByRole('button', { name: 'Check access' })).toBeDisabled()
  })

  it('renders resource type options from resource actions', async () => {
    const user = userEvent.setup()
    render(<CheckAccessView {...sampleResourceActions} />, { wrapper })

    // Open the typeahead to see options
    await user.click(screen.getByPlaceholderText('Select a resource type'))

    expect(screen.getByRole('option', { name: /^project$/i })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: /^workflow$/i })).toBeInTheDocument()
  })

  it('populates actions when resource type is selected', async () => {
    const user = userEvent.setup()
    render(<CheckAccessView {...sampleResourceActions} />, { wrapper })

    await user.click(screen.getByPlaceholderText('Select a resource type'))
    await user.click(screen.getByRole('option', { name: /workflow/i }))

    // Workflow has read and write actions
    await user.click(screen.getByPlaceholderText('Select an action'))
    expect(screen.getByRole('option', { name: /read/i })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: /write/i })).toBeInTheDocument()
  })

  it('auto-selects action when only one is available', async () => {
    const user = userEvent.setup()
    render(<CheckAccessView {...sampleResourceActions} />, { wrapper })

    // project only has 'read' action - should auto-select
    await user.click(screen.getByPlaceholderText('Select a resource type'))
    await user.click(screen.getByRole('option', { name: /^project$/i }))

    await waitFor(() => {
      const actionInput = screen.getByPlaceholderText('Select an action')
      expect(actionInput).toHaveValue('read')
    })
  })

  it('shows grey matched policy label on allowed result', () => {
    mockMutationState({
      isSuccess: true,
      data: { allowed: true, denied: false, matched_policy: 'admin-policy', denial_reason: '', denied_by: '' },
      variables: sampleCheckAccessRequest,
    })

    render(<CheckAccessView {...sampleResourceActions} />, { wrapper })

    expect(screen.getByText('admin-policy', { selector: '.pf-v6-c-label__text' })).toBeInTheDocument()
  })

  it('shows access allowed result with project name', () => {
    mockMutationState({
      isSuccess: true,
      data: { allowed: true, denied: false, matched_policy: 'admin-policy', denial_reason: '', denied_by: '' },
      variables: sampleCheckAccessRequest,
    })

    render(<CheckAccessView {...sampleResourceActions} />, { wrapper })

    expect(screen.getByText('Access allowed')).toBeInTheDocument()
    expect(screen.getByText('admin-policy')).toBeInTheDocument()
    expect(screen.getByText(/in project/)).toBeInTheDocument()
    expect(screen.getByText('default')).toBeInTheDocument()
  })

  it('shows grey denied-by and matched policy labels on denied result', () => {
    mockMutationState({
      isSuccess: true,
      data: {
        allowed: false,
        denied: true,
        matched_policy: 'deny-policy',
        denial_reason: 'Explicitly denied',
        denied_by: 'deny-policy',
      },
      variables: sampleCheckAccessRequest,
    })

    render(<CheckAccessView {...sampleResourceActions} />, { wrapper })

    expect(screen.getAllByText('deny-policy', { selector: '.pf-v6-c-label__text' })).toHaveLength(2)
  })

  it('shows access denied result with project name', () => {
    mockMutationState({
      isSuccess: true,
      data: {
        allowed: false,
        denied: true,
        matched_policy: 'deny-policy',
        denial_reason: 'Explicitly denied',
        denied_by: 'deny-policy',
      },
      variables: sampleCheckAccessRequest,
    })

    render(<CheckAccessView {...sampleResourceActions} />, { wrapper })

    expect(screen.getByText('Access denied')).toBeInTheDocument()
    expect(screen.getByText(/Explicitly denied/)).toBeInTheDocument()
    expect(screen.getAllByText('deny-policy')).toHaveLength(2)
    expect(screen.getByText(/in project/)).toBeInTheDocument()
    expect(screen.getByText('default')).toBeInTheDocument()
  })

  it('shows "in any project" when no project is specified', () => {
    mockMutationState({
      isSuccess: true,
      data: {
        allowed: false,
        denied: false,
        matched_policy: '',
        denial_reason: '',
        denied_by: '',
      },
      variables: { body: { action: 'read', resource_type: 'project' } },
    })

    render(<CheckAccessView {...sampleResourceActions} />, { wrapper })

    expect(screen.getByText('Access not granted')).toBeInTheDocument()
    expect(screen.getByText(/in any project/)).toBeInTheDocument()
  })

  it('shows error state when API call fails', () => {
    mockMutationState({
      isError: true,
      error: new Error('Server error'),
    })

    render(<CheckAccessView {...sampleResourceActions} />, { wrapper })

    expect(screen.getByText('Access check failed')).toBeInTheDocument()
  })

  it('shows spinner while checking access', () => {
    mockMutationState({ isPending: true, isIdle: false })

    render(<CheckAccessView {...sampleResourceActions} />, { wrapper })

    expect(screen.getByRole('progressbar', { name: 'Checking access' })).toBeInTheDocument()
  })

  it('calls mutate with correct params on submit', async () => {
    const user = userEvent.setup()
    render(<CheckAccessView {...sampleResourceActions} />, { wrapper })

    await fillForm(user)
    await user.click(screen.getByRole('button', { name: 'Check access' }))

    await waitFor(() => {
      expect(mockMutate).toHaveBeenCalledWith(
        expect.objectContaining({
          // eslint-disable-next-line @typescript-eslint/no-unsafe-assignment
          body: expect.objectContaining({
            action: 'read',
            resource_type: 'project',
          }),
        })
      )
    })
  })

  it('renders with empty resource actions', async () => {
    const user = userEvent.setup()
    render(<CheckAccessView resourceTypes={[]} actionsByResource={new Map()} />, { wrapper })

    // Open typeahead - should show no results
    await user.click(screen.getByPlaceholderText('Select a resource type'))
    expect(screen.getByText(/No results match/)).toBeInTheDocument()
  })

  it('has no accessibility violations', async () => {
    const { container } = render(<CheckAccessView {...sampleResourceActions} />, { wrapper })
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  describe('field help popovers', () => {
    it('shows resource type, action, project, and resource id help on click', async () => {
      const user = userEvent.setup()
      render(<CheckAccessView {...sampleResourceActions} />, { wrapper })

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
