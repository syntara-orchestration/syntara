import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { AlertProvider } from '../../providers/alerts'
import { accessClient } from '../access/accessClient'
import type { ProjectRead } from '../access/types'

import { PROJECT_NAME_HELP } from './projectFieldHelp'
import { ProjectFormModal } from './ProjectFormModal'
import { PROJECT_NAME_HINT, PROJECT_NAME_VALIDATION_MESSAGE } from './projectFormSchema'

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

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
})

const wrapper = ({ children }: { children: ReactNode }) => (
  <QueryClientProvider client={queryClient}>
    <AlertProvider>{children}</AlertProvider>
  </QueryClientProvider>
)

describe('ProjectFormModal', () => {
  const mockCreateMutate = vi.fn()
  const mockUpdateMutate = vi.fn()
  const mockOnClose = vi.fn()
  const mockOnSuccess = vi.fn()

  const mockProject: ProjectRead = {
    id: 'p1',
    name: 'Alpha',
    description: 'Alpha project',
    labels: {},
    is_default: false,
    created_at: '2024-01-01T00:00:00Z',
    updated_at: '2024-01-02T00:00:00Z',
  }

  beforeEach(() => {
    vi.clearAllMocks()

    vi.mocked(accessClient.useMutation).mockImplementation(((_method: string, endpoint: string) => {
      if (endpoint === '/projects') {
        return {
          mutate: mockCreateMutate,
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
        }
      }
      return {
        mutate: mockUpdateMutate,
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
      }
    }) as never)
  })

  describe('Create Mode', () => {
    it('renders with "Create project" title when no project is provided', () => {
      render(<ProjectFormModal isOpen={true} onClose={mockOnClose} onSuccess={mockOnSuccess} />, { wrapper })

      expect(screen.getByRole('heading', { name: 'Create project' })).toBeInTheDocument()
      expect(screen.getByRole('button', { name: 'Create project' })).toBeInTheDocument()
    })

    it('renders form fields with placeholders and name format hint', () => {
      render(<ProjectFormModal isOpen={true} onClose={mockOnClose} onSuccess={mockOnSuccess} />, { wrapper })

      expect(screen.getByPlaceholderText('project-name')).toBeInTheDocument()
      expect(screen.getByText(PROJECT_NAME_HINT)).toBeInTheDocument()
      expect(screen.getByPlaceholderText('Enter description')).toBeInTheDocument()
    })

    it('shows project name help body on click while keeping format hint inline', async () => {
      const user = userEvent.setup()
      render(<ProjectFormModal isOpen={true} onClose={mockOnClose} onSuccess={mockOnSuccess} />, { wrapper })

      expect(screen.getByText(PROJECT_NAME_HINT)).toBeInTheDocument()
      await user.click(screen.getByRole('button', { name: 'More info for Project name' }))
      expect(screen.getByText(PROJECT_NAME_HELP)).toBeInTheDocument()
      expect(screen.getByText(PROJECT_NAME_HINT)).toBeInTheDocument()
    })

    it('does not submit when required name field is empty', async () => {
      const user = userEvent.setup()
      render(<ProjectFormModal isOpen={true} onClose={mockOnClose} onSuccess={mockOnSuccess} />, { wrapper })

      await user.click(screen.getByRole('button', { name: 'Create project' }))

      await waitFor(() => {
        expect(mockCreateMutate).not.toHaveBeenCalled()
      })
    })

    it('shows validation error when name is empty', async () => {
      const user = userEvent.setup()
      render(<ProjectFormModal isOpen={true} onClose={mockOnClose} onSuccess={mockOnSuccess} />, { wrapper })

      await user.click(screen.getByRole('button', { name: 'Create project' }))

      await waitFor(() => {
        expect(screen.getByText('Project name is required')).toBeInTheDocument()
      })
      expect(screen.queryByText(PROJECT_NAME_HINT)).not.toBeInTheDocument()
    })

    it('shows human-readable error for names with spaces', async () => {
      const user = userEvent.setup()
      render(<ProjectFormModal isOpen={true} onClose={mockOnClose} onSuccess={mockOnSuccess} />, { wrapper })

      await user.type(screen.getByRole('textbox', { name: 'Project name' }), 'linux team')
      await user.click(screen.getByRole('button', { name: 'Create project' }))

      await waitFor(() => {
        expect(screen.getByText(PROJECT_NAME_VALIDATION_MESSAGE)).toBeInTheDocument()
      })
      expect(mockCreateMutate).not.toHaveBeenCalled()
    })

    it('shows human-readable error for names starting with hyphen', async () => {
      const user = userEvent.setup()
      render(<ProjectFormModal isOpen={true} onClose={mockOnClose} onSuccess={mockOnSuccess} />, { wrapper })

      await user.type(screen.getByRole('textbox', { name: 'Project name' }), '-invalid')
      await user.click(screen.getByRole('button', { name: 'Create project' }))

      await waitFor(() => {
        expect(screen.getByText(/must start and end with a letter or number/)).toBeInTheDocument()
      })
      expect(mockCreateMutate).not.toHaveBeenCalled()
    })

    it('shows human-readable error for names with special characters', async () => {
      const user = userEvent.setup()
      render(<ProjectFormModal isOpen={true} onClose={mockOnClose} onSuccess={mockOnSuccess} />, { wrapper })

      await user.type(screen.getByRole('textbox', { name: 'Project name' }), 'test@project')
      await user.click(screen.getByRole('button', { name: 'Create project' }))

      await waitFor(() => {
        expect(screen.getByText(/can only contain letters, numbers, hyphens/)).toBeInTheDocument()
      })
      expect(mockCreateMutate).not.toHaveBeenCalled()
    })

    it('calls create mutation with form data on submit', async () => {
      const user = userEvent.setup()
      render(<ProjectFormModal isOpen={true} onClose={mockOnClose} onSuccess={mockOnSuccess} />, { wrapper })

      await user.type(screen.getByRole('textbox', { name: 'Project name' }), 'new-project')
      await user.type(screen.getByRole('textbox', { name: 'Description' }), 'A description')
      await user.click(screen.getByRole('button', { name: 'Create project' }))

      await waitFor(() => {
        expect(mockCreateMutate).toHaveBeenCalled()
        const callArgs = mockCreateMutate.mock.calls[0]
        expect(callArgs[0]).toEqual({
          body: { name: 'new-project', description: 'A description' },
        })
      })
    })

    it('calls onClose and onSuccess after successful create', async () => {
      const user = userEvent.setup()
      const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries')
      render(<ProjectFormModal isOpen={true} onClose={mockOnClose} onSuccess={mockOnSuccess} />, { wrapper })

      await user.type(screen.getByRole('textbox', { name: 'Project name' }), 'new-project')
      await user.click(screen.getByRole('button', { name: 'Create project' }))

      await waitFor(() => {
        expect(mockCreateMutate).toHaveBeenCalled()
      })

      await waitFor(() => {
        const callbacks = mockCreateMutate.mock.calls[0][1] as { onSuccess: () => void }
        callbacks.onSuccess()
      })

      expect(mockOnClose).toHaveBeenCalled()
      expect(mockOnSuccess).toHaveBeenCalled()
      expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['all-projects'] })
    })

    it('calls error handler on failed create', async () => {
      const user = userEvent.setup()
      render(<ProjectFormModal isOpen={true} onClose={mockOnClose} onSuccess={mockOnSuccess} />, { wrapper })

      await user.type(screen.getByRole('textbox', { name: 'Project name' }), 'new-project')
      await user.click(screen.getByRole('button', { name: 'Create project' }))

      await waitFor(() => {
        expect(mockCreateMutate).toHaveBeenCalled()
        const callbacks = mockCreateMutate.mock.calls[0][1] as { onError: (err: Error) => void }
        expect(callbacks.onError).toBeDefined()
      })
    })
  })

  describe('Edit Mode', () => {
    it('renders with "Edit project" title when project is provided', () => {
      render(<ProjectFormModal project={mockProject} isOpen={true} onClose={mockOnClose} onSuccess={mockOnSuccess} />, {
        wrapper,
      })

      expect(screen.getByText('Edit Alpha')).toBeInTheDocument()
      expect(screen.getByRole('button', { name: 'Save project' })).toBeInTheDocument()
    })

    it('pre-populates form fields with project data', () => {
      render(<ProjectFormModal project={mockProject} isOpen={true} onClose={mockOnClose} onSuccess={mockOnSuccess} />, {
        wrapper,
      })

      expect(screen.getByPlaceholderText('project-name')).toHaveValue('Alpha')
      expect(screen.getByPlaceholderText('Enter description')).toHaveValue('Alpha project')
    })

    it('shows project name help body on click', async () => {
      const user = userEvent.setup()
      render(<ProjectFormModal project={mockProject} isOpen={true} onClose={mockOnClose} onSuccess={mockOnSuccess} />, {
        wrapper,
      })

      await user.click(screen.getByRole('button', { name: 'More info for Project name' }))
      expect(screen.getByText(PROJECT_NAME_HELP)).toBeInTheDocument()
    })

    it('calls update mutation with form data on submit', async () => {
      const user = userEvent.setup()
      render(<ProjectFormModal project={mockProject} isOpen={true} onClose={mockOnClose} onSuccess={mockOnSuccess} />, {
        wrapper,
      })

      const nameInput = screen.getByPlaceholderText('project-name')
      await user.clear(nameInput)
      await user.type(nameInput, 'updated-alpha')
      await user.click(screen.getByRole('button', { name: 'Save project' }))

      await waitFor(() => {
        expect(mockUpdateMutate).toHaveBeenCalled()
        const callArgs = mockUpdateMutate.mock.calls[0]
        expect(callArgs[0]).toEqual({
          params: { path: { project_id: 'p1' } },
          body: { name: 'updated-alpha', description: 'Alpha project' },
        })
      })
    })

    it('calls onClose and onSuccess after successful update', async () => {
      const user = userEvent.setup()
      const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries')
      render(<ProjectFormModal project={mockProject} isOpen={true} onClose={mockOnClose} onSuccess={mockOnSuccess} />, {
        wrapper,
      })

      await user.click(screen.getByRole('button', { name: 'Save project' }))

      await waitFor(() => {
        expect(mockUpdateMutate).toHaveBeenCalled()
      })

      await waitFor(() => {
        const callbacks = mockUpdateMutate.mock.calls[0][1] as { onSuccess: () => void }
        callbacks.onSuccess()
      })

      expect(mockOnClose).toHaveBeenCalled()
      expect(mockOnSuccess).toHaveBeenCalled()
      expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['all-projects'] })
    })

    it('resets form when modal opens with different project', () => {
      const Wrapper = wrapper
      const { rerender } = render(
        <Wrapper>
          <ProjectFormModal isOpen={true} onClose={mockOnClose} onSuccess={mockOnSuccess} />
        </Wrapper>
      )

      expect(screen.getByPlaceholderText('project-name')).toHaveValue('')

      rerender(
        <Wrapper>
          <ProjectFormModal project={mockProject} isOpen={true} onClose={mockOnClose} onSuccess={mockOnSuccess} />
        </Wrapper>
      )

      expect(screen.getByPlaceholderText('project-name')).toHaveValue('Alpha')
      expect(screen.getByPlaceholderText('Enter description')).toHaveValue('Alpha project')
    })
  })

  describe('Modal Behavior', () => {
    it('does not render content when isOpen is false', () => {
      render(<ProjectFormModal isOpen={false} onClose={mockOnClose} onSuccess={mockOnSuccess} />, { wrapper })

      expect(screen.queryByRole('heading', { name: 'Create project' })).not.toBeInTheDocument()
    })

    it('calls onClose when Cancel button is clicked', async () => {
      const user = userEvent.setup()
      render(<ProjectFormModal isOpen={true} onClose={mockOnClose} onSuccess={mockOnSuccess} />, { wrapper })

      await user.click(screen.getByRole('button', { name: 'Cancel' }))

      expect(mockOnClose).toHaveBeenCalled()
    })
  })

  describe('Accessibility', () => {
    it('has no accessibility violations in create mode', async () => {
      const { container } = render(<ProjectFormModal isOpen={true} onClose={mockOnClose} onSuccess={mockOnSuccess} />, {
        wrapper,
      })

      const results = await axe(container)
      expect(results).toHaveNoViolations()
    })

    it('has no accessibility violations in edit mode', async () => {
      const { container } = render(
        <ProjectFormModal project={mockProject} isOpen={true} onClose={mockOnClose} onSuccess={mockOnSuccess} />,
        { wrapper }
      )

      const results = await axe(container)
      expect(results).toHaveNoViolations()
    })
  })
})
