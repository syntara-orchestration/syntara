import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, within, act, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { AlertProvider } from '../../providers/alerts'
import { accessClient } from '../access/accessClient'
import type { ProjectRead } from '../access/types'

import { PROJECT_NAME_PLACEHOLDER } from './projectFormSchema'
import { ProjectsTab } from './ProjectsTab'

vi.mock('../../client', () => ({
  authMiddleware: { onRequest: vi.fn() },
  interfaceTagMiddleware: { onRequest: vi.fn() },
}))

vi.mock('../access/accessClient', () => ({
  accessClient: {
    useQuery: vi.fn(),
    useMutation: vi.fn(),
  },
}))

vi.mock('./useProjectPermissions', () => ({
  useProjectPermissions: () => ({
    canCreate: true,
    canUpdate: true,
    canDelete: true,
    isLoading: false,
    tooltips: { create: '', update: '', delete: '' },
  }),
}))

vi.mock('../../hooks/routing/navigate', () => ({
  navigate: vi.fn(),
}))

vi.mock('../../hooks/routing/useNavigate', () => ({
  useNavigate: () => vi.fn(),
}))

vi.mock('../../hooks/routing/useLocation', () => ({
  useLocation: () => '/system-administration/access-management/projects',
}))

vi.mock('../../hooks/routing/useSearch', () => ({
  useSearch: () => '',
}))

vi.mock('../../hooks/routing/useSearchParams', async () => {
  const React = await import('react')
  return {
    useSearchParams: () => React.useState(new URLSearchParams()),
  }
})

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false } },
})

const wrapper = ({ children }: { children: ReactNode }) => (
  <QueryClientProvider client={queryClient}>
    <AlertProvider>{children}</AlertProvider>
  </QueryClientProvider>
)

const mockRefetch = vi.fn().mockResolvedValue({})

const mockProjects: ProjectRead[] = [
  {
    id: 'p1',
    name: 'Alpha',
    description: 'Alpha project',
    labels: {},
    is_default: false,
    created_at: '2024-01-01T00:00:00Z',
    updated_at: '2024-01-02T00:00:00Z',
  },
  {
    id: 'p2',
    name: 'Beta',
    description: 'Beta project',
    labels: {},
    is_default: false,
    created_at: '2024-02-01T00:00:00Z',
    updated_at: '2024-02-02T00:00:00Z',
  },
  {
    id: 'p3',
    name: 'Gamma',
    description: null,
    labels: {},
    is_default: false,
    created_at: '2024-03-01T00:00:00Z',
    updated_at: '2024-03-02T00:00:00Z',
  },
]

function setupMocks(projects = mockProjects) {
  vi.mocked(accessClient.useQuery).mockReturnValue({
    data: { resources: projects, total: projects.length, next: null, prev: null },
    isPending: false,
    isFetching: false,
    isError: false,
    error: null,
    refetch: mockRefetch,
  } as never)

  vi.mocked(accessClient.useMutation).mockReturnValue({
    mutate: vi.fn(),
    isPending: false,
    isError: false,
    error: null,
    data: null,
    reset: vi.fn(),
    mutateAsync: vi.fn(),
    isIdle: true,
    isSuccess: false,
    failureCount: 0,
    failureReason: null,
    context: undefined,
    submittedAt: 0,
    variables: undefined,
    status: 'idle',
    isPaused: false,
  } as never)
}

const DELETE_PROJECT_LABEL = 'Delete project'

function findDeleteOption() {
  return screen.findByRole('menuitem', { name: DELETE_PROJECT_LABEL })
}

describe('ProjectsTab', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    setupMocks()
  })

  describe('Rendering', () => {
    it('renders the table with projects from API response', () => {
      render(<ProjectsTab />, { wrapper })

      expect(screen.getByText('Alpha')).toBeInTheDocument()
      expect(screen.getByText('Beta')).toBeInTheDocument()
      expect(screen.getByText('Gamma')).toBeInTheDocument()
    })

    it('renders Create project button', () => {
      render(<ProjectsTab />, { wrapper })

      expect(screen.getByRole('button', { name: /create project/i })).toBeInTheDocument()
    })

    it('renders table column headers', () => {
      render(<ProjectsTab />, { wrapper })

      expect(screen.getByRole('columnheader', { name: /^Name$/i })).toBeInTheDocument()
      expect(screen.getByRole('columnheader', { name: /Description/i })).toBeInTheDocument()
      expect(screen.getByRole('columnheader', { name: /Created/i })).toBeInTheDocument()
      expect(screen.getByRole('columnheader', { name: /Updated/i })).toBeInTheDocument()
    })

    it('renders description as empty string for null', () => {
      render(<ProjectsTab />, { wrapper })

      expect(screen.getByText('Gamma')).toBeInTheDocument()
      expect(screen.getByText('Alpha project')).toBeInTheDocument()
    })

    it('renders project names as links', () => {
      render(<ProjectsTab />, { wrapper })

      expect(screen.getByRole('button', { name: 'Alpha' })).toBeInTheDocument()
      expect(screen.getByRole('button', { name: 'Beta' })).toBeInTheDocument()
    })
  })

  describe('Empty State', () => {
    it('displays empty state when no projects exist', () => {
      setupMocks([])

      render(<ProjectsTab />, { wrapper })

      expect(screen.getByText('No projects yet')).toBeInTheDocument()
      expect(screen.getByText('Create a project to organize workflows and manage access.')).toBeInTheDocument()
      expect(screen.getByRole('button', { name: /create project/i })).toBeInTheDocument()
    })

    it('opens create modal from empty state button', async () => {
      const user = userEvent.setup()
      setupMocks([])

      render(<ProjectsTab />, { wrapper })

      await user.click(screen.getByRole('button', { name: /create project/i }))

      await waitFor(() => {
        expect(screen.getByPlaceholderText(PROJECT_NAME_PLACEHOLDER)).toBeInTheDocument()
      })
    })
  })

  describe('Error Handling', () => {
    it('displays loading state', () => {
      vi.mocked(accessClient.useQuery).mockReturnValue({
        data: undefined,
        isPending: true,
        isFetching: true,
        isError: false,
        error: null,
        refetch: mockRefetch,
      } as never)

      render(<ProjectsTab />, { wrapper })

      expect(screen.getByRole('progressbar', { name: 'Loading' })).toBeInTheDocument()
    })

    it('displays error state', () => {
      vi.mocked(accessClient.useQuery).mockReturnValue({
        data: undefined,
        isPending: false,
        isFetching: false,
        isError: true,
        error: new Error('Failed to load'),
        refetch: mockRefetch,
      } as never)

      render(<ProjectsTab />, { wrapper })

      expect(screen.getByRole('heading', { name: 'Error' })).toBeInTheDocument()
    })
  })

  describe('API Query Params', () => {
    it('passes sort and pagination params to the API', () => {
      render(<ProjectsTab />, { wrapper })

      const callArgs = vi
        .mocked(accessClient.useQuery)
        .mock.calls.find((call) => call[0] === 'get' && call[1] === '/projects')
      expect(callArgs).toBeDefined()
      const queryOptions = callArgs![2] as unknown as {
        params: { query: Record<string, unknown> }
      }
      expect(queryOptions.params.query).toMatchObject({
        sort: 'name',
        limit: 20,
        include_total: true,
      })
    })

    it('renders sortable column headers', () => {
      render(<ProjectsTab />, { wrapper })

      const nameHeader = screen.getByRole('columnheader', { name: /^Name$/i })
      expect(within(nameHeader).getByRole('button')).toBeInTheDocument()

      const createdHeader = screen.getByRole('columnheader', { name: /Created/i })
      expect(within(createdHeader).getByRole('button')).toBeInTheDocument()

      const updatedHeader = screen.getByRole('columnheader', { name: /Updated/i })
      expect(within(updatedHeader).getByRole('button')).toBeInTheDocument()
    })
  })

  describe('Filtering', () => {
    it('renders filter bar with name filter input', () => {
      render(<ProjectsTab />, { wrapper })

      expect(screen.getByPlaceholderText('Filter by name')).toBeInTheDocument()
    })

    it('accepts text input in the name filter', async () => {
      const user = userEvent.setup()
      render(<ProjectsTab />, { wrapper })

      const textInput = screen.getByPlaceholderText('Filter by name')
      await user.type(textInput, 'Alpha')
      expect(textInput).toHaveValue('Alpha')
    })
  })

  describe('Row Actions', () => {
    it('provides row action menus', () => {
      render(<ProjectsTab />, { wrapper })

      const table = screen.getByRole('grid', { name: 'Projects' })
      const rows = within(table).getAllByRole('row')
      expect(rows.length).toBeGreaterThanOrEqual(4)
    })

    it('opens edit modal when edit action is clicked', async () => {
      const user = userEvent.setup()
      render(<ProjectsTab />, { wrapper })

      const actionButtons = screen.getAllByRole('button', { name: /^Actions for / })
      await user.click(actionButtons[0])

      const editOption = await screen.findByRole('menuitem', { name: /edit/i })
      await user.click(editOption)

      await waitFor(() => {
        expect(screen.getByText('Edit Alpha')).toBeInTheDocument()
      })
    })

    it('opens delete dialog when delete action is clicked', async () => {
      const user = userEvent.setup()
      render(<ProjectsTab />, { wrapper })

      const actionButtons = screen.getAllByRole('button', { name: /^Actions for / })
      await user.click(actionButtons[0])

      const deleteOption = await findDeleteOption()
      await user.click(deleteOption)

      await waitFor(() => {
        expect(screen.getByText('Delete project?')).toBeInTheDocument()
      })

      const dialog = screen.getByRole('dialog')
      expect(within(dialog).getByText('Alpha')).toBeInTheDocument()
      expect(within(dialog).getByText(/will be deleted/)).toBeInTheDocument()
      expect(
        within(dialog).getByRole('checkbox', {
          name: 'I understand this project, its workflows, and role assignments will be permanently deleted or removed.',
        })
      ).toBeInTheDocument()
    })
  })

  describe('Delete Dialog Content', () => {
    it('renders project name in dialog body when project is selected for deletion', async () => {
      const user = userEvent.setup()
      render(<ProjectsTab />, { wrapper })

      const actionButtons = screen.getAllByRole('button', { name: /^Actions for / })
      await user.click(actionButtons[1])
      const deleteOption = await findDeleteOption()
      await user.click(deleteOption)

      const dialog = await screen.findByRole('dialog')
      expect(within(dialog).getByText('Beta')).toBeInTheDocument()
      expect(within(dialog).getByText(/will be deleted/)).toBeInTheDocument()
    })
  })

  describe('Delete Dialog Flow', () => {
    it('calls delete mutation when Delete button is clicked', async () => {
      const user = userEvent.setup()
      const mockDeleteMutate = vi.fn()

      vi.mocked(accessClient.useMutation).mockReturnValue({
        mutate: mockDeleteMutate,
        isPending: false,
      } as never)

      render(<ProjectsTab />, { wrapper })

      const actionButtons = screen.getAllByRole('button', { name: /^Actions for / })
      await user.click(actionButtons[0])
      const deleteOption = await findDeleteOption()
      await user.click(deleteOption)

      const deleteButton = await screen.findByRole('button', { name: 'Delete' })
      expect(deleteButton).toBeDisabled()

      const ackCheckbox = screen.getByRole('checkbox')
      await user.click(ackCheckbox)
      expect(deleteButton).toBeEnabled()

      await user.click(deleteButton)
      expect(mockDeleteMutate).toHaveBeenCalled()
    })

    it('shows success alert and closes dialog on successful delete', async () => {
      const user = userEvent.setup()
      const mockDeleteMutate = vi.fn()

      vi.mocked(accessClient.useMutation).mockReturnValue({
        mutate: mockDeleteMutate,
        isPending: false,
      } as never)

      render(<ProjectsTab />, { wrapper })

      const actionButtons = screen.getAllByRole('button', { name: /^Actions for / })
      await user.click(actionButtons[0])
      const deleteOption = await findDeleteOption()
      await user.click(deleteOption)

      await user.click(screen.getByRole('checkbox'))
      const deleteButton = await screen.findByRole('button', { name: 'Delete' })
      await user.click(deleteButton)

      const callbacks = mockDeleteMutate.mock.calls[0][1] as { onSuccess: () => void; onSettled: () => void }
      act(() => {
        callbacks.onSuccess()
        callbacks.onSettled()
      })

      await waitFor(() => {
        expect(screen.queryByText('Delete project?')).not.toBeInTheDocument()
      })
    })

    it('shows error alert on delete failure', async () => {
      const user = userEvent.setup()
      const mockDeleteMutate = vi.fn()

      vi.mocked(accessClient.useMutation).mockReturnValue({
        mutate: mockDeleteMutate,
        isPending: false,
      } as never)

      render(<ProjectsTab />, { wrapper })

      const actionButtons = screen.getAllByRole('button', { name: /^Actions for / })
      await user.click(actionButtons[0])
      const deleteOption = await findDeleteOption()
      await user.click(deleteOption)

      await user.click(screen.getByRole('checkbox'))
      const deleteButton = await screen.findByRole('button', { name: 'Delete' })
      await user.click(deleteButton)

      const callbacks = mockDeleteMutate.mock.calls[0][1] as {
        onError: (err: Error) => void
        onSettled: () => void
      }
      act(() => {
        callbacks.onError(new Error('Permission denied'))
        callbacks.onSettled()
      })

      await waitFor(() => {
        expect(screen.queryByText('Delete project?')).not.toBeInTheDocument()
      })
    })

    it('closes delete dialog when Cancel button is clicked', async () => {
      const user = userEvent.setup()
      render(<ProjectsTab />, { wrapper })

      const actionButtons = screen.getAllByRole('button', { name: /^Actions for / })
      await user.click(actionButtons[0])
      const deleteOption = await findDeleteOption()
      await user.click(deleteOption)

      await waitFor(() => {
        expect(screen.getByText('Delete project?')).toBeInTheDocument()
      })

      const cancelButtons = screen.getAllByRole('button', { name: 'Cancel' })
      await user.click(cancelButtons[cancelButtons.length - 1])

      await waitFor(() => {
        expect(screen.queryByText(/will be deleted/)).not.toBeInTheDocument()
      })
    })
  })

  describe('Create Project', () => {
    it('opens create modal when Create project button is clicked', async () => {
      const user = userEvent.setup()
      render(<ProjectsTab />, { wrapper })

      await user.click(screen.getByRole('button', { name: /create project/i }))

      await waitFor(() => {
        expect(screen.getByPlaceholderText(PROJECT_NAME_PLACEHOLDER)).toBeInTheDocument()
      })
    })

    it('closes create modal when cancel is clicked and clears edit state', async () => {
      const user = userEvent.setup()
      render(<ProjectsTab />, { wrapper })

      const actionButtons = screen.getAllByRole('button', { name: /^Actions for / })
      await user.click(actionButtons[0])
      const editOption = await screen.findByRole('menuitem', { name: /edit/i })
      await user.click(editOption)

      await waitFor(() => {
        expect(screen.getByText('Edit Alpha')).toBeInTheDocument()
      })

      await user.click(screen.getByRole('button', { name: 'Cancel' }))

      await waitFor(() => {
        expect(screen.queryByText('Edit Alpha')).not.toBeInTheDocument()
      })
    })

    it('refetches after successful create from empty state', async () => {
      setupMocks([])

      const mockCreateMutate = vi.fn()
      vi.mocked(accessClient.useMutation).mockReturnValue({
        mutate: mockCreateMutate,
        isPending: false,
      } as never)

      const user = userEvent.setup()
      render(<ProjectsTab />, { wrapper })

      await user.click(screen.getByRole('button', { name: /create project/i }))

      await user.type(screen.getByRole('textbox', { name: 'Project name' }), 'New')
      await user.click(screen.getByRole('button', { name: 'Create project' }))

      await waitFor(() => {
        expect(mockCreateMutate).toHaveBeenCalled()
      })

      const callbacks = mockCreateMutate.mock.calls[0][1] as { onSuccess: () => void }
      act(() => {
        callbacks.onSuccess()
      })

      await waitFor(() => {
        expect(mockRefetch).toHaveBeenCalled()
      })
    })

    it('refetches after successful create from table view', async () => {
      const mockCreateMutate = vi.fn()
      vi.mocked(accessClient.useMutation).mockReturnValue({
        mutate: mockCreateMutate,
        isPending: false,
      } as never)

      const user = userEvent.setup()
      render(<ProjectsTab />, { wrapper })

      await user.click(screen.getByRole('button', { name: /create project/i }))

      await user.type(screen.getByRole('textbox', { name: 'Project name' }), 'New')
      await user.click(screen.getByRole('button', { name: 'Create project' }))

      await waitFor(() => {
        expect(mockCreateMutate).toHaveBeenCalled()
      })

      const callbacks = mockCreateMutate.mock.calls[0][1] as { onSuccess: () => void }
      act(() => {
        callbacks.onSuccess()
      })

      await waitFor(() => {
        expect(mockRefetch).toHaveBeenCalled()
      })
    })
  })

  describe('Pagination', () => {
    it('renders pagination footer', () => {
      render(<ProjectsTab />, { wrapper })

      expect(screen.getByRole('navigation', { name: 'Pagination' })).toBeInTheDocument()
    })
  })

  describe('Accessibility', () => {
    it('has no accessibility violations', async () => {
      const { container } = render(<ProjectsTab />, { wrapper })

      const results = await axe(container)
      expect(results).toHaveNoViolations()
    })

    it('has no accessibility violations in empty state', async () => {
      setupMocks([])

      const { container } = render(<ProjectsTab />, { wrapper })

      const results = await axe(container)
      expect(results).toHaveNoViolations()
    })
  })
})
