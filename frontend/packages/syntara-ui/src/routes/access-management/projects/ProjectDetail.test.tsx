import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { AlertProvider } from '../../../providers/alerts'
import { routerTestState } from '../../../test/setup'
import { accessClient, accessFetchClient } from '../../access/accessClient'
import { useProjectPermissions } from '../useProjectPermissions'

import { ProjectDetail } from './ProjectDetail'

vi.mock('../../access/accessClient', () => ({
  accessClient: {
    useQuery: vi.fn(),
    useMutation: vi.fn(),
  },
  accessFetchClient: {
    POST: vi.fn(),
  },
}))

vi.mock('../../../client', () => ({
  authMiddleware: { onRequest: vi.fn() },
  interfaceTagMiddleware: { onRequest: vi.fn() },
}))

const { mockUseParams } = vi.hoisted(() => ({
  mockUseParams: vi.fn(() => ({ projectId: 'proj-1' })),
}))

vi.mock('@tanstack/react-router', async () => {
  const actual = await vi.importActual('@tanstack/react-router')
  const { routerTestState, MockLink } = await import('../../../test/setup')
  return {
    ...actual,
    Link: MockLink,
    useParams: () => mockUseParams(),
    useNavigate: () => routerTestState.navigate,
  }
})

vi.mock('../../../hooks/routing/useLocation', () => ({
  useLocation: () => '/system-administration/access-management/projects/proj-1/details',
}))

const mockGoToTab = vi.fn()
const mockDetailTab = vi.fn(() => ['details', mockGoToTab])
vi.mock('../../../hooks/useUrlTab', () => ({
  useUrlTab: () => mockDetailTab(),
}))

vi.mock('./ProjectRoleAssignmentsTab', () => ({
  ProjectRoleAssignmentsTab: () => <div>Mock Role Assignments Tab</div>,
}))

vi.mock('./ProjectNotFoundState', () => ({
  ProjectNotFoundState: ({ onBack, onRetry }: { onBack: () => void; onRetry: () => void }) => (
    <div>
      <span>Project not found</span>
      <button type="button" onClick={onBack}>
        Back to projects
      </button>
      <button type="button" onClick={onRetry}>
        Retry
      </button>
    </div>
  ),
}))

vi.mock('../ProjectFormModal', () => ({
  ProjectFormModal: ({ isOpen, onClose }: { isOpen: boolean; onClose: () => void }) =>
    isOpen ? (
      <div data-testid="project-form-modal">
        <button type="button" onClick={onClose}>
          Close modal
        </button>
      </div>
    ) : null,
}))

vi.mock('../useProjectPermissions')

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false } },
})

const wrapper = ({ children }: { children: ReactNode }) => (
  <QueryClientProvider client={queryClient}>
    <AlertProvider>{children}</AlertProvider>
  </QueryClientProvider>
)

const mockProject = {
  id: 'proj-1',
  name: 'Alpha Project',
  description: 'Test project',
  is_default: false,
  labels: { env: 'prod' },
  created_at: '2024-01-01T00:00:00Z',
  updated_at: '2024-06-01T00:00:00Z',
}

describe('ProjectDetail', () => {
  const mockRefetch = vi.fn().mockResolvedValue({})

  function setupMocks(project = mockProject) {
    vi.mocked(accessClient.useQuery).mockReturnValue({
      data: project,
      isLoading: false,
      isError: false,
      error: null,
      refetch: mockRefetch,
    } as never)
  }

  beforeEach(() => {
    vi.clearAllMocks()
    queryClient.clear()
    mockRefetch.mockResolvedValue({})
    mockDetailTab.mockReturnValue(['details', mockGoToTab])
    mockUseParams.mockReturnValue({ projectId: 'proj-1' })
    vi.mocked(accessFetchClient.POST).mockResolvedValue({ data: { allowed: true } } as never)
    vi.mocked(useProjectPermissions).mockReturnValue({
      canCreate: true,
      canUpdate: true,
      canDelete: true,
      isLoading: false,
      tooltips: { create: '', update: '', delete: '' },
    })
    vi.mocked(accessClient.useMutation).mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
    } as never)
    setupMocks()
  })

  it('renders toolbar with Edit project button and kebab menu', () => {
    render(<ProjectDetail />, { wrapper })

    expect(screen.getByRole('button', { name: 'Edit project' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Project actions' })).toBeInTheDocument()
  })

  it('opens edit modal when Edit project is clicked', async () => {
    const user = userEvent.setup()
    render(<ProjectDetail />, { wrapper })

    await user.click(screen.getByRole('button', { name: 'Edit project' }))

    expect(screen.getByTestId('project-form-modal')).toBeInTheDocument()
  })

  it('disables Edit project button when canUpdate is false', () => {
    vi.mocked(useProjectPermissions).mockReturnValue({
      canCreate: true,
      canUpdate: false,
      canDelete: true,
      isLoading: false,
      tooltips: { create: '', update: 'Insufficient permissions', delete: '' },
    })

    render(<ProjectDetail />, { wrapper })

    expect(screen.getByRole('button', { name: 'Edit project' })).toHaveAttribute('aria-disabled', 'true')
  })

  it('opens delete confirmation dialog from kebab menu', async () => {
    const user = userEvent.setup()
    render(<ProjectDetail />, { wrapper })

    await user.click(screen.getByRole('button', { name: 'Project actions' }))
    await user.click(screen.getByRole('menuitem', { name: /delete project/i }))

    expect(screen.getByText('Delete project?')).toBeInTheDocument()
  })

  it('closes delete confirmation dialog when Cancel is clicked', async () => {
    const user = userEvent.setup()
    render(<ProjectDetail />, { wrapper })

    await user.click(screen.getByRole('button', { name: 'Project actions' }))
    await user.click(screen.getByRole('menuitem', { name: /delete project/i }))
    expect(screen.getByText('Delete project?')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(screen.queryByText('Delete project?')).not.toBeInTheDocument()
  })

  it('disables delete action in kebab menu when canDelete is false', async () => {
    vi.mocked(useProjectPermissions).mockReturnValue({
      canCreate: true,
      canUpdate: true,
      canDelete: false,
      isLoading: false,
      tooltips: { create: '', update: '', delete: 'Insufficient permissions' },
    })

    const user = userEvent.setup()
    render(<ProjectDetail />, { wrapper })

    await user.click(screen.getByRole('button', { name: 'Project actions' }))
    expect(screen.getByRole('menuitem', { name: /delete project/i })).toHaveAttribute('aria-disabled', 'true')
  })

  it('has no accessibility violations', async () => {
    const { container } = render(<ProjectDetail />, { wrapper })
    let results: Awaited<ReturnType<typeof axe>>
    await act(async () => {
      // PF6 Tabs generates aria-controls referencing tab panel IDs that jsdom
      // does not render (lazy panels), causing a false-positive violation.
      results = await axe(container, {
        rules: { 'aria-valid-attr-value': { enabled: false } },
      })
    })
    expect(results!).toHaveNoViolations()
  })

  it('renders project name as heading', () => {
    render(<ProjectDetail />, { wrapper })

    expect(screen.getByRole('heading', { name: 'Alpha Project' })).toBeInTheDocument()
  })

  it('renders Details tab content with description', () => {
    render(<ProjectDetail />, { wrapper })

    expect(screen.getByText('Test project')).toBeInTheDocument()
  })

  it('renders labels in Details tab', () => {
    render(<ProjectDetail />, { wrapper })

    expect(screen.getByText('env: prod')).toBeInTheDocument()
  })

  it('renders tab navigation buttons', () => {
    render(<ProjectDetail />, { wrapper })

    expect(screen.getByRole('tab', { name: 'Details' })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'Assignments' })).toBeInTheDocument()
  })

  it('shows not-found state when query has an error', () => {
    vi.mocked(accessClient.useQuery).mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
      error: new Error('Not found'),
      refetch: mockRefetch,
    } as never)

    render(<ProjectDetail />, { wrapper })

    expect(screen.getByText('Project not found')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Back to projects' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument()
  })

  it('renders loading state while data is pending', () => {
    vi.mocked(accessClient.useQuery).mockReturnValue({
      data: undefined,
      isLoading: false,
      isPending: true,
      isError: false,
      error: null,
      refetch: mockRefetch,
    } as never)

    render(<ProjectDetail />, { wrapper })

    expect(screen.queryByRole('heading', { name: 'Alpha Project' })).not.toBeInTheDocument()
    expect(screen.getByRole('progressbar', { name: 'Loading' })).toBeInTheDocument()
  })

  it('renders nothing when data is undefined with no error and not pending', () => {
    vi.mocked(accessClient.useQuery).mockReturnValue({
      data: undefined,
      isLoading: false,
      isPending: false,
      isError: false,
      error: null,
      refetch: mockRefetch,
    } as never)

    const { container } = render(<ProjectDetail />, { wrapper })

    expect(container).toBeEmptyDOMElement()
  })

  it('renders "-" for labels when project has no labels', () => {
    const projectNoLabels = { ...mockProject, labels: {} }
    vi.mocked(accessClient.useQuery).mockReturnValue({
      data: projectNoLabels,
      isLoading: false,
      isError: false,
      error: null,
      refetch: mockRefetch,
    } as never)

    render(<ProjectDetail />, { wrapper })

    expect(screen.getAllByText('-').length).toBeGreaterThan(0)
  })

  it('calls refetchProject when retry is clicked in not-found state', async () => {
    const user = userEvent.setup()
    vi.mocked(accessClient.useQuery).mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
      error: new Error('Not found'),
      refetch: mockRefetch,
    } as never)

    render(<ProjectDetail />, { wrapper })

    await user.click(screen.getByRole('button', { name: 'Retry' }))

    expect(mockRefetch).toHaveBeenCalled()
  })

  it('calls navigate when back button is clicked in not-found state', async () => {
    const user = userEvent.setup()
    vi.mocked(accessClient.useQuery).mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
      error: new Error('Not found'),
      refetch: mockRefetch,
    } as never)

    render(<ProjectDetail />, { wrapper })

    await user.click(screen.getByRole('button', { name: 'Back to projects' }))

    expect(routerTestState.navigate).toHaveBeenCalledWith({ to: '/system-administration/access-management/projects' })
  })

  it('renders "-" for description when project has no description', () => {
    const projectNoDesc = { ...mockProject, description: null }
    vi.mocked(accessClient.useQuery).mockReturnValue({
      data: projectNoDesc,
      isLoading: false,
      isError: false,
      error: null,
      refetch: mockRefetch,
    } as never)

    render(<ProjectDetail />, { wrapper })

    expect(screen.getByText('Description')).toBeInTheDocument()
    // When description is null, the ?? fallback shows '-'
    const dashes = screen.getAllByText('-')
    expect(dashes.length).toBeGreaterThan(0)
  })

  it('renders the Role Assignments tab content', () => {
    mockDetailTab.mockReturnValue(['role-assignments', mockGoToTab])
    render(<ProjectDetail />, { wrapper })

    expect(screen.getByText('Mock Role Assignments Tab')).toBeInTheDocument()
  })

  it('calls goToTab when a tab is clicked', async () => {
    const user = userEvent.setup()
    render(<ProjectDetail />, { wrapper })

    await user.click(screen.getByRole('tab', { name: 'Assignments' }))

    expect(mockGoToTab).toHaveBeenCalledWith('role-assignments')
  })

  it('handles refetch rejection gracefully in onRetry callback', async () => {
    const user = userEvent.setup()
    const rejectingRefetch = vi.fn().mockRejectedValue(new Error('Refetch failed'))
    vi.mocked(accessClient.useQuery).mockReturnValue({
      data: undefined,
      isLoading: false,
      isPending: false,
      isError: true,
      error: { message: 'Not found', retryable: true },
      refetch: rejectingRefetch,
    } as never)

    render(<ProjectDetail />, { wrapper })

    // Click retry in the queryState error (not the not-found state)
    // With isError=true AND error being set, projectQuery.error branch is taken
    await user.click(screen.getByRole('button', { name: 'Retry' }))
    expect(rejectingRefetch).toHaveBeenCalled()
  })

  it('handles refetch rejection in not-found state onRetry', async () => {
    const user = userEvent.setup()
    const rejectingRefetch = vi.fn().mockRejectedValue(new Error('Refetch failed'))
    vi.mocked(accessClient.useQuery).mockReturnValue({
      data: undefined,
      isLoading: false,
      isPending: false,
      isError: true,
      error: new Error('Not found'),
      refetch: rejectingRefetch,
    } as never)

    render(<ProjectDetail />, { wrapper })

    await user.click(screen.getByRole('button', { name: 'Retry' }))
    expect(rejectingRefetch).toHaveBeenCalled()
  })

  it('renders with undefined projectId gracefully', () => {
    mockUseParams.mockReturnValue({ projectId: undefined as unknown as string })
    vi.mocked(accessClient.useQuery).mockReturnValue({
      data: undefined,
      isLoading: false,
      isPending: false,
      isError: false,
      error: null,
      refetch: mockRefetch,
    } as never)

    const { container } = render(<ProjectDetail />, { wrapper })

    // With no projectId, data is undefined and no error → returns null
    expect(container).toBeEmptyDOMElement()
  })

  it('renders "-" for labels when labels is undefined', () => {
    const projectUndefinedLabels = { ...mockProject, labels: undefined as unknown as Record<string, unknown> }
    vi.mocked(accessClient.useQuery).mockReturnValue({
      data: projectUndefinedLabels,
      isLoading: false,
      isError: false,
      error: null,
      refetch: mockRefetch,
    } as never)

    render(<ProjectDetail />, { wrapper })

    // When labels is undefined, the ?? {} fallback is used → empty labels → shows '-'
    const dashes = screen.getAllByText('-')
    expect(dashes.length).toBeGreaterThan(0)
  })

  it('renders grey Default label when project is_default', () => {
    const defaultProject = { ...mockProject, is_default: true }
    vi.mocked(accessClient.useQuery).mockReturnValue({
      data: defaultProject,
      isLoading: false,
      isError: false,
      error: null,
      refetch: mockRefetch,
    } as never)

    render(<ProjectDetail />, { wrapper })

    expect(screen.getByText('Default', { selector: '.pf-v6-c-label__text' })).toBeInTheDocument()
  })

  describe('Permission-based tab gating', () => {
    it('hides Assignments tab when role-assignment:read is denied', async () => {
      vi.mocked(accessFetchClient.POST).mockResolvedValue({ data: { allowed: false } } as never)
      render(<ProjectDetail />, { wrapper })

      await waitFor(() => {
        expect(screen.queryByRole('tab', { name: /Assignments/ })).not.toBeInTheDocument()
      })
      expect(screen.getByRole('tab', { name: /Details/ })).toBeInTheDocument()
    })

    it('shows Assignments tab when role-assignment:read is granted', async () => {
      vi.mocked(accessFetchClient.POST).mockResolvedValue({ data: { allowed: true } } as never)
      render(<ProjectDetail />, { wrapper })

      await waitFor(() => {
        expect(screen.getByRole('tab', { name: /Assignments/ })).toBeInTheDocument()
      })
    })
  })
})
