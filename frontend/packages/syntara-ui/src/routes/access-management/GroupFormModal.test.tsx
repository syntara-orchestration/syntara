import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { AlertProvider } from '../../providers/alerts'
import { accessClient } from '../access/accessClient'

import { GROUP_NAME_HELP } from './groupFieldHelpText'
import { GroupFormModal } from './GroupFormModal'

// Mock dependencies
vi.mock('../../client', () => ({
  usersClient: {
    useMutation: vi.fn(),
  },
  authMiddleware: { onRequest: vi.fn() },
  interfaceTagMiddleware: { onRequest: vi.fn() },
}))

vi.mock('../access/accessClient', () => ({
  accessClient: {
    useQuery: vi.fn(),
    useMutation: vi.fn(),
  },
}))

// Create a QueryClient instance
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: false,
    },
    mutations: {
      retry: false,
    },
  },
})

const wrapper = ({ children }: { children: ReactNode }) => (
  <QueryClientProvider client={queryClient}>
    <AlertProvider>{children}</AlertProvider>
  </QueryClientProvider>
)

describe('GroupFormModal Component', () => {
  const mockCreateMutate = vi.fn()
  const mockUpdateMutate = vi.fn()
  const mockOnClose = vi.fn()
  const mockOnSuccess = vi.fn()

  const mockGroup = {
    id: 'g1',
    name: 'Admins',
    description: 'Administrator group',
    is_builtin: false,
    created_at: '2024-01-01T00:00:00Z',
    updated_at: '2024-01-02T00:00:00Z',
  }

  beforeEach(() => {
    vi.clearAllMocks()

    vi.mocked(accessClient.useMutation).mockImplementation(((_method: string, endpoint: string) => {
      if (endpoint === '/groups') {
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
    it('renders with "Create group" title when no group is provided', () => {
      render(<GroupFormModal isOpen={true} onClose={mockOnClose} onSuccess={mockOnSuccess} />, { wrapper })

      expect(screen.getByRole('heading', { name: 'Create group' })).toBeInTheDocument()
      expect(screen.getByRole('button', { name: 'Create group' })).toBeInTheDocument()
    })

    it('renders form fields', () => {
      render(<GroupFormModal isOpen={true} onClose={mockOnClose} onSuccess={mockOnSuccess} />, { wrapper })

      expect(screen.getByPlaceholderText('Enter group name')).toBeInTheDocument()
      expect(screen.getByPlaceholderText('Enter description')).toBeInTheDocument()
    })

    it('shows group name help body on click', async () => {
      const user = userEvent.setup()
      render(<GroupFormModal isOpen={true} onClose={mockOnClose} onSuccess={mockOnSuccess} />, { wrapper })

      await user.click(screen.getByRole('button', { name: 'More info for Group name' }))
      expect(screen.getByText(GROUP_NAME_HELP)).toBeInTheDocument()
    })

    it('does not submit when required fields are empty', async () => {
      const user = userEvent.setup()
      render(<GroupFormModal isOpen={true} onClose={mockOnClose} onSuccess={mockOnSuccess} />, { wrapper })

      const submitButton = screen.getByRole('button', { name: 'Create group' })
      expect(submitButton).toBeEnabled()

      await user.click(submitButton)

      await waitFor(() => {
        expect(mockCreateMutate).not.toHaveBeenCalled()
      })
    })

    it('calls create mutation with form data on submit', async () => {
      const user = userEvent.setup()
      render(<GroupFormModal isOpen={true} onClose={mockOnClose} onSuccess={mockOnSuccess} />, { wrapper })

      const nameInput = screen.getByRole('textbox', { name: 'Group name' })
      const descInput = screen.getByRole('textbox', { name: 'Description' })

      await user.click(nameInput)
      await user.keyboard('New Group')
      await user.click(descInput)
      await user.keyboard('A new group')

      await user.click(screen.getByRole('button', { name: 'Create group' }))

      await waitFor(() => {
        expect(mockCreateMutate).toHaveBeenCalled()
        const callArgs = mockCreateMutate.mock.calls[0]
        expect(callArgs[0]).toEqual({
          body: {
            name: 'New Group',
            description: 'A new group',
          },
        })
      })
    })

    it('calls onClose and onSuccess after successful create', async () => {
      const user = userEvent.setup()
      render(<GroupFormModal isOpen={true} onClose={mockOnClose} onSuccess={mockOnSuccess} />, { wrapper })

      await user.click(screen.getByRole('textbox', { name: 'Group name' }))
      await user.keyboard('New Group')

      await user.click(screen.getByRole('button', { name: 'Create group' }))

      await waitFor(() => {
        expect(mockCreateMutate).toHaveBeenCalled()
      })

      // Simulate successful mutation callback inside waitFor so React
      // state updates (showAlert) are wrapped in act() automatically
      await waitFor(() => {
        const callbacks = mockCreateMutate.mock.calls[0][1] as { onSuccess: () => void }
        callbacks.onSuccess()
      })

      expect(mockOnClose).toHaveBeenCalled()
      expect(mockOnSuccess).toHaveBeenCalled()
    })
  })

  describe('Edit Mode', () => {
    it('renders with "Edit group" title when group is provided', () => {
      render(<GroupFormModal group={mockGroup} isOpen={true} onClose={mockOnClose} onSuccess={mockOnSuccess} />, {
        wrapper,
      })

      expect(screen.getByText('Edit Admins')).toBeInTheDocument()
      expect(screen.getByText('Save')).toBeInTheDocument()
    })

    it('pre-populates form fields with group data', () => {
      render(<GroupFormModal group={mockGroup} isOpen={true} onClose={mockOnClose} onSuccess={mockOnSuccess} />, {
        wrapper,
      })

      expect(screen.getByPlaceholderText('Enter group name')).toHaveValue('Admins')
      expect(screen.getByPlaceholderText('Enter description')).toHaveValue('Administrator group')
    })

    it('shows group name help body on click', async () => {
      const user = userEvent.setup()
      render(<GroupFormModal group={mockGroup} isOpen={true} onClose={mockOnClose} onSuccess={mockOnSuccess} />, {
        wrapper,
      })

      await user.click(screen.getByRole('button', { name: 'More info for Group name' }))
      expect(screen.getByText(GROUP_NAME_HELP)).toBeInTheDocument()
    })

    it('calls update mutation with form data on submit', async () => {
      const user = userEvent.setup()
      render(<GroupFormModal group={mockGroup} isOpen={true} onClose={mockOnClose} onSuccess={mockOnSuccess} />, {
        wrapper,
      })

      const nameInput = screen.getByPlaceholderText('Enter group name')
      await user.clear(nameInput)
      await user.type(nameInput, 'Updated Admins')

      // Query by role rather than by the button's text: the text lives in a nested span
      // (PatternFly wraps button labels), and happy-dom's implicit-submit handling only
      // fires for a click whose target is the submit button element itself.
      await user.click(screen.getByRole('button', { name: 'Save' }))

      await waitFor(() => {
        expect(mockUpdateMutate).toHaveBeenCalled()
        const callArgs = mockUpdateMutate.mock.calls[0]
        expect(callArgs[0]).toEqual({
          params: { path: { group_id: 'g1' } },
          body: {
            name: 'Updated Admins',
            description: 'Administrator group',
          },
        })
      })
    })

    it('populates form fields when group prop changes without remounting', () => {
      const Wrapper = wrapper
      const { rerender } = render(
        <Wrapper>
          <GroupFormModal isOpen={true} onClose={mockOnClose} onSuccess={mockOnSuccess} />
        </Wrapper>
      )

      // Initially in create mode — fields should be empty
      expect(screen.getByPlaceholderText('Enter group name')).toHaveValue('')

      // Rerender with a group to simulate switching to edit mode
      rerender(
        <Wrapper>
          <GroupFormModal group={mockGroup} isOpen={true} onClose={mockOnClose} onSuccess={mockOnSuccess} />
        </Wrapper>
      )

      // Fields should now reflect the group data
      expect(screen.getByPlaceholderText('Enter group name')).toHaveValue('Admins')
      expect(screen.getByPlaceholderText('Enter description')).toHaveValue('Administrator group')
    })

    it('calls onClose and onSuccess after successful update', async () => {
      const user = userEvent.setup()
      render(<GroupFormModal group={mockGroup} isOpen={true} onClose={mockOnClose} onSuccess={mockOnSuccess} />, {
        wrapper,
      })

      const nameInput = screen.getByPlaceholderText('Enter group name')
      await user.clear(nameInput)
      await user.type(nameInput, 'Updated Admins')

      // Query by role rather than by the button's text: the text lives in a nested span
      // (PatternFly wraps button labels), and happy-dom's implicit-submit handling only
      // fires for a click whose target is the submit button element itself.
      await user.click(screen.getByRole('button', { name: 'Save' }))

      await waitFor(() => {
        expect(mockUpdateMutate).toHaveBeenCalled()
      })

      // Simulate successful mutation callback inside waitFor so React
      // state updates (showAlert) are wrapped in act() automatically
      await waitFor(() => {
        const callbacks = mockUpdateMutate.mock.calls[0][1] as { onSuccess: () => void }
        callbacks.onSuccess()
      })

      expect(mockOnClose).toHaveBeenCalled()
      expect(mockOnSuccess).toHaveBeenCalled()
    })
  })

  describe('Modal Behavior', () => {
    it('does not render content when isOpen is false', () => {
      render(<GroupFormModal isOpen={false} onClose={mockOnClose} onSuccess={mockOnSuccess} />, { wrapper })

      expect(screen.queryByText('Create group')).not.toBeInTheDocument()
    })

    it('calls onClose when Cancel button is clicked', async () => {
      const user = userEvent.setup()
      render(<GroupFormModal isOpen={true} onClose={mockOnClose} onSuccess={mockOnSuccess} />, { wrapper })

      await user.click(screen.getByText('Cancel'))

      expect(mockOnClose).toHaveBeenCalled()
    })
  })

  describe('Validation', () => {
    it('shows error when group name is empty', async () => {
      const user = userEvent.setup()
      render(<GroupFormModal isOpen={true} onClose={mockOnClose} onSuccess={mockOnSuccess} />, { wrapper })

      await user.click(screen.getByRole('button', { name: 'Create group' }))

      await waitFor(() => {
        expect(screen.getByText('Group name is required')).toBeInTheDocument()
      })

      expect(mockCreateMutate).not.toHaveBeenCalled()
    })
  })

  describe('Accessibility', () => {
    it('has no accessibility violations in create mode', async () => {
      const { container } = render(<GroupFormModal isOpen={true} onClose={mockOnClose} onSuccess={mockOnSuccess} />, {
        wrapper,
      })

      const results = await axe(container)
      expect(results).toHaveNoViolations()
    })

    it('has no accessibility violations in edit mode', async () => {
      const { container } = render(
        <GroupFormModal group={mockGroup} isOpen={true} onClose={mockOnClose} onSuccess={mockOnSuccess} />,
        { wrapper }
      )

      const results = await axe(container)
      expect(results).toHaveNoViolations()
    })
  })
})
