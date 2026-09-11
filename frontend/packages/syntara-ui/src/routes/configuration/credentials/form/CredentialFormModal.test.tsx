import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactNode } from 'react'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { axe } from 'vitest-axe'

import { credentialsClient } from '../../../../client'
import { AlertProvider } from '../../../../providers/alerts'
import { useSelectableProjects } from '../../../access/useAllProjects'

import { CredentialFormModal } from './CredentialFormModal'

vi.mock('../../../../client', () => ({
  credentialsClient: {
    useQuery: vi.fn(),
    useMutation: vi.fn(),
  },
}))

vi.mock('../../../access/useAllProjects', () => ({
  useSelectableProjects: vi.fn(),
}))

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false } },
})

const wrapper = ({ children }: { children: ReactNode }) => (
  <QueryClientProvider client={queryClient}>
    <AlertProvider>{children}</AlertProvider>
  </QueryClientProvider>
)

const mockTypes = [
  {
    id: 'type-1',
    name: 'HTTP Bearer Token',
    description: 'Bearer token authentication for HTTP APIs',
    inputs: {
      fields: [{ id: 'token', label: 'Token', type: 'string', secret: true, help_text: 'Bearer token value' }],
      required: ['token'],
    },
    injectors: {},
    managed: true,
  },
  {
    id: 'type-2',
    name: 'HTTP Basic Auth',
    description: 'Username and password',
    inputs: {
      fields: [
        { id: 'username', label: 'Username', type: 'string', secret: false },
        { id: 'password', label: 'Password', type: 'string', secret: true },
      ],
      required: ['username', 'password'],
    },
    injectors: {},
    managed: true,
  },
  {
    id: 'type-aap',
    name: 'Ansible Automation Platform',
    description: 'AAP API access',
    inputs: {
      fields: [
        { id: 'username', label: 'Username', type: 'string', secret: false },
        { id: 'password', label: 'Password', type: 'string', secret: true },
        { id: 'oauth_token', label: 'OAuth Token', type: 'string', secret: true },
      ],
      required: [],
      mutually_exclusive: [['oauth_token'], ['username', 'password']],
      mutually_exclusive_labels: ['OAuth2 Token', 'Basic Auth'],
      mutually_exclusive_help:
        'Basic Auth authenticates with username and password. OAuth2 Token uses a personal access token.',
      required_one_of: [['oauth_token'], ['username', 'password']],
      required_together: [['username', 'password']],
    },
    injectors: {},
    managed: true,
  },
]

const mockProjects = [
  { id: 'proj-1', name: 'Project Alpha' },
  { id: 'proj-2', name: 'Project Beta' },
  { id: 'proj-3', name: 'Project Gamma' },
]

const mockCredential = {
  id: 'cred-1',
  name: 'My Token',
  description: 'A test token',
  credential_type_id: 'type-1',
  inputs: { token: '$encrypted$' },
  enabled: true,
  labels: {},
  created_by: { id: '550e8400-e29b-41d4-a716-446655440001', name: 'user-1' },
  project_id: 'proj-1',
  created_at: '2026-03-01T00:00:00Z',
  updated_at: '2026-03-01T00:00:00Z',
} as const

describe('CredentialFormModal', () => {
  let mockMutate: ReturnType<typeof vi.fn>

  beforeEach(() => {
    vi.clearAllMocks()
    mockMutate = vi.fn()

    vi.mocked(credentialsClient.useQuery).mockReturnValue({
      data: { resources: mockTypes },
      isLoading: false,
      error: null,
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
    } as any)
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    vi.mocked(credentialsClient.useMutation).mockReturnValue({ mutate: mockMutate, isPending: false } as any)
    const projectsMock = { projects: mockProjects, isLoading: false, error: null, refetch: vi.fn() }
    // eslint-disable-next-line @typescript-eslint/no-unsafe-argument, @typescript-eslint/no-explicit-any
    vi.mocked(useSelectableProjects).mockReturnValue(projectsMock as any)
  })

  it('has no accessibility violations in create mode', async () => {
    const { container } = render(<CredentialFormModal isOpen onClose={vi.fn()} />, { wrapper })
    expect(await axe(container)).toHaveNoViolations()
  })

  it('has no accessibility violations in edit mode', async () => {
    const { container } = render(<CredentialFormModal isOpen onClose={vi.fn()} credentialToEdit={mockCredential} />, {
      wrapper,
    })
    expect(await axe(container)).toHaveNoViolations()
  })

  it('renders create modal title when no credential provided', () => {
    render(<CredentialFormModal isOpen onClose={vi.fn()} />, { wrapper })
    expect(screen.getByRole('dialog')).toBeInTheDocument()
    // Title and button both say "Create credential" — check the modal header specifically
    const dialog = screen.getByRole('dialog')
    expect(
      within(dialog).getByText('Create credential', { selector: '.pf-v6-c-modal-box__title-text' })
    ).toBeInTheDocument()
  })

  it('renders edit modal title when credential provided', () => {
    render(<CredentialFormModal isOpen onClose={vi.fn()} credentialToEdit={mockCredential} />, { wrapper })
    expect(screen.getByText('Edit My Token')).toBeInTheDocument()
  })

  it('renders name and description fields', () => {
    render(<CredentialFormModal isOpen onClose={vi.fn()} />, { wrapper })
    expect(screen.getByLabelText('Credential name')).toBeInTheDocument()
    expect(screen.getByLabelText('Credential description')).toBeInTheDocument()
  })

  it('renders credential type dropdown with types', async () => {
    const user = userEvent.setup()
    render(<CredentialFormModal isOpen onClose={vi.fn()} />, { wrapper })
    const typeToggle = screen.getByLabelText('Credential type')
    expect(typeToggle).toBeInTheDocument()
    // Auto-selects first type, shown in toggle
    expect(typeToggle).toHaveTextContent('HTTP Bearer Token')

    // Open dropdown to verify all options are listed
    await user.click(typeToggle)
    const listbox = screen.getByRole('listbox', { name: 'Credential type options' })
    expect(within(listbox).getByText('HTTP Bearer Token')).toBeInTheDocument()
    expect(within(listbox).getByText('HTTP Basic Auth')).toBeInTheDocument()
  })

  it('portals the credential type menu outside the modal (avoids modal body scroll)', async () => {
    const user = userEvent.setup()
    render(<CredentialFormModal isOpen onClose={vi.fn()} />, { wrapper })

    await user.click(screen.getByLabelText('Credential type'))

    const dialog = screen.getByRole('dialog')
    const listbox = screen.getByRole('listbox', { name: 'Credential type options' })
    expect(within(dialog).queryByRole('listbox', { name: 'Credential type options' })).not.toBeInTheDocument()
    expect(listbox).toBeInTheDocument()
  })

  it('closes the open select when scrolling outside the menu in the modal', async () => {
    const user = userEvent.setup()
    render(<CredentialFormModal isOpen onClose={vi.fn()} />, { wrapper })

    await user.click(screen.getByLabelText('Credential type'))
    expect(screen.getByRole('listbox', { name: 'Credential type options' })).toBeInTheDocument()

    const dialog = screen.getByRole('dialog')
    act(() => {
      dialog.dispatchEvent(new WheelEvent('wheel', { bubbles: true, cancelable: true }))
    })

    await waitFor(() => {
      expect(screen.queryByRole('listbox', { name: 'Credential type options' })).not.toBeInTheDocument()
    })
  })

  it('shows dynamic fields when type is selected', () => {
    render(<CredentialFormModal isOpen onClose={vi.fn()} />, { wrapper })

    // Auto-selects type-1 (HTTP Bearer Token) on mount, so Token field should be visible
    expect(screen.getByLabelText('Token', { selector: 'input' })).toBeInTheDocument()
  })

  it('shows multiple fields for multi-field type', async () => {
    const user = userEvent.setup()
    render(<CredentialFormModal isOpen onClose={vi.fn()} />, { wrapper })

    // Open dropdown and select HTTP Basic Auth
    await user.click(screen.getByLabelText('Credential type'))
    await user.click(screen.getByRole('option', { name: 'HTTP Basic Auth' }))

    expect(screen.getByLabelText('Username', { selector: 'input' })).toBeInTheDocument()
    expect(screen.getByLabelText('Password', { selector: 'input' })).toBeInTheDocument()
  })

  it('pre-fills fields in edit mode', () => {
    render(<CredentialFormModal isOpen onClose={vi.fn()} credentialToEdit={mockCredential} />, { wrapper })

    expect(screen.getByDisplayValue('My Token')).toBeInTheDocument()
    expect(screen.getByDisplayValue('A test token')).toBeInTheDocument()
  })

  it('disables type dropdown in edit mode', () => {
    render(<CredentialFormModal isOpen onClose={vi.fn()} credentialToEdit={mockCredential} />, { wrapper })

    const typeSelect = screen.getByLabelText('Credential type')
    expect(typeSelect).toBeDisabled()
  })

  it('shows create button in create mode', () => {
    render(<CredentialFormModal isOpen onClose={vi.fn()} />, { wrapper })
    expect(screen.getByRole('button', { name: 'Create credential' })).toBeInTheDocument()
  })

  it('shows save button in edit mode', () => {
    render(<CredentialFormModal isOpen onClose={vi.fn()} credentialToEdit={mockCredential} />, { wrapper })
    expect(screen.getByRole('button', { name: 'Save credential' })).toBeInTheDocument()
  })

  it('calls onClose when cancel is clicked', async () => {
    const user = userEvent.setup()
    const onClose = vi.fn()
    render(<CredentialFormModal isOpen onClose={onClose} />, { wrapper })

    await user.click(screen.getByRole('button', { name: 'Cancel' }))

    expect(onClose).toHaveBeenCalledOnce()
  })

  it('validates required name field', async () => {
    const user = userEvent.setup()
    render(<CredentialFormModal isOpen onClose={vi.fn()} />, { wrapper })

    await user.click(screen.getByRole('button', { name: 'Create credential' }))

    expect(screen.getByText('Name is required')).toBeInTheDocument()
  })

  it('auto-selects first credential type in create mode', () => {
    render(<CredentialFormModal isOpen onClose={vi.fn()} />, { wrapper })

    // PF6 Select shows the selected type name in the toggle
    expect(screen.getByLabelText('Credential type')).toHaveTextContent('HTTP Bearer Token')
  })

  it('shows loading placeholder when types are loading', () => {
    vi.mocked(credentialsClient.useQuery).mockReturnValue({
      data: undefined,
      isLoading: true,
      error: null,
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
    } as any)

    render(<CredentialFormModal isOpen onClose={vi.fn()} />, { wrapper })

    expect(screen.getByText('Loading types...')).toBeInTheDocument()
  })

  it('shows error when types fail to load', () => {
    vi.mocked(credentialsClient.useQuery).mockReturnValue({
      data: undefined,
      isLoading: false,
      error: new Error('Network error'),
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
    } as any)

    render(<CredentialFormModal isOpen onClose={vi.fn()} />, { wrapper })

    expect(screen.getByText('Failed to load credential types')).toBeInTheDocument()
  })

  it('calls create mutation with correct data', async () => {
    const user = userEvent.setup()
    render(<CredentialFormModal isOpen onClose={vi.fn()} defaultProjectId="proj-1" />, { wrapper })

    await user.type(screen.getByLabelText('Credential name'), 'New Token')
    // type-1 (HTTP Bearer Token) is auto-selected, no need to re-select
    await user.type(screen.getByLabelText('Token', { selector: 'input' }), 'my-secret-token')
    await user.click(screen.getByRole('button', { name: 'Create credential' }))

    await waitFor(() => expect(mockMutate).toHaveBeenCalled())
    // eslint-disable-next-line @typescript-eslint/no-unsafe-assignment
    const callArgs = mockMutate.mock.calls[0][0]
    expect(callArgs).toHaveProperty('body.name', 'New Token')
    expect(callArgs).toHaveProperty('body.credential_type_id', 'type-1')
    expect(callArgs).toHaveProperty('body.project_id', 'proj-1')
  })

  it('does not render when isOpen is false', () => {
    render(<CredentialFormModal isOpen={false} onClose={vi.fn()} />, { wrapper })

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('calls patch mutation in edit mode', async () => {
    const user = userEvent.setup()
    render(<CredentialFormModal isOpen onClose={vi.fn()} credentialToEdit={mockCredential} />, { wrapper })

    await user.clear(screen.getByDisplayValue('My Token'))
    await user.type(screen.getByLabelText('Credential name'), 'Updated Token')
    await user.click(screen.getByRole('button', { name: 'Save credential' }))

    await waitFor(() => expect(mockMutate).toHaveBeenCalled())
  })

  it('calls onSuccess callback after successful create', async () => {
    const onSuccess = vi.fn()
    const onClose = vi.fn()
    // Make mutate call onSuccess immediately
    mockMutate.mockImplementation((_args: unknown, callbacks: { onSuccess: () => void }) => {
      callbacks.onSuccess()
    })

    const user = userEvent.setup()
    render(<CredentialFormModal isOpen onClose={onClose} onSuccess={onSuccess} defaultProjectId="proj-1" />, {
      wrapper,
    })

    await user.type(screen.getByLabelText('Credential name'), 'New Token')
    // type-1 (HTTP Bearer Token) is auto-selected
    await user.type(screen.getByLabelText('Token', { selector: 'input' }), 'secret')
    await user.click(screen.getByRole('button', { name: 'Create credential' }))

    await waitFor(() => expect(onSuccess).toHaveBeenCalled())
    expect(onClose).toHaveBeenCalled()
  })

  it('resets form when type changes in create mode', async () => {
    const user = userEvent.setup()
    render(<CredentialFormModal isOpen onClose={vi.fn()} />, { wrapper })

    // First type (HTTP Bearer Token) is auto-selected
    expect(screen.getByLabelText('Token', { selector: 'input' })).toBeInTheDocument()

    // Change to second type via PF6 Select
    await user.click(screen.getByLabelText('Credential type'))
    await user.click(screen.getByRole('option', { name: 'HTTP Basic Auth' }))
    expect(screen.getByLabelText('Username', { selector: 'input' })).toBeInTheDocument()
    expect(screen.getByLabelText('Password', { selector: 'input' })).toBeInTheDocument()
    expect(screen.queryByLabelText('Token', { selector: 'input' })).not.toBeInTheDocument()
  })

  it('clears field errors when input changes', async () => {
    const user = userEvent.setup()
    render(<CredentialFormModal isOpen onClose={vi.fn()} />, { wrapper })

    // Trigger validation error
    await user.click(screen.getByRole('button', { name: 'Create credential' }))
    expect(screen.getByText('Name is required')).toBeInTheDocument()

    // Type in name to clear error
    await user.type(screen.getByLabelText('Credential name'), 'Test')
    expect(screen.queryByText('Name is required')).not.toBeInTheDocument()
  })

  it('pre-selects credential type when preSelectedTypeId is provided', () => {
    render(<CredentialFormModal isOpen onClose={vi.fn()} preSelectedTypeId="type-1" />, { wrapper })

    const typeToggle = screen.getByLabelText('Credential type')
    expect(typeToggle).toHaveTextContent('HTTP Bearer Token')
    expect(typeToggle).toBeDisabled()
  })

  it('shows dynamic fields for pre-selected type', () => {
    render(<CredentialFormModal isOpen onClose={vi.fn()} preSelectedTypeId="type-1" />, { wrapper })

    expect(screen.getByLabelText('Token', { selector: 'input' })).toBeInTheDocument()
  })

  it('renders project dropdown in create mode', async () => {
    const user = userEvent.setup()
    render(<CredentialFormModal isOpen onClose={vi.fn()} />, { wrapper })

    const projectToggle = screen.getByRole('button', { name: 'Credential project' })
    expect(projectToggle).toBeInTheDocument()
    expect(projectToggle).toHaveTextContent('Select a project')

    // Open dropdown to verify all options are listed
    await user.click(projectToggle)
    expect(screen.getByRole('option', { name: 'Project Alpha' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'Project Beta' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'Project Gamma' })).toBeInTheDocument()
  })

  it('pre-selects project when defaultProjectId is provided', () => {
    render(<CredentialFormModal isOpen onClose={vi.fn()} defaultProjectId="proj-1" />, { wrapper })

    expect(screen.getByRole('button', { name: 'Credential project' })).toHaveTextContent('Project Alpha')
  })

  it('shows placeholder when no defaultProjectId is provided', () => {
    render(<CredentialFormModal isOpen onClose={vi.fn()} />, { wrapper })

    expect(screen.getByLabelText('Credential project')).toHaveValue('')
    expect(screen.getByText('Select a project')).toBeInTheDocument()
  })

  it('validates project field is required in create mode', async () => {
    const user = userEvent.setup()
    render(<CredentialFormModal isOpen onClose={vi.fn()} />, { wrapper })

    await user.type(screen.getByLabelText('Credential name'), 'New Token')
    // type-1 (HTTP Bearer Token) is auto-selected
    await user.type(screen.getByLabelText('Token', { selector: 'input' }), 'my-secret-token')
    await user.click(screen.getByRole('button', { name: 'Create credential' }))

    expect(screen.getByText('Project is required')).toBeInTheDocument()
  })

  it('includes project_id from form in create payload', async () => {
    const user = userEvent.setup()
    render(<CredentialFormModal isOpen onClose={vi.fn()} defaultProjectId="proj-1" />, { wrapper })

    await user.type(screen.getByLabelText('Credential name'), 'New Token')
    // type-1 (HTTP Bearer Token) is auto-selected
    await user.type(screen.getByLabelText('Token', { selector: 'input' }), 'my-secret-token')
    await user.click(screen.getByRole('button', { name: 'Create credential' }))

    await waitFor(() => expect(mockMutate).toHaveBeenCalled())
    // eslint-disable-next-line @typescript-eslint/no-unsafe-assignment
    const callArgs = mockMutate.mock.calls[0][0]
    expect(callArgs).toHaveProperty('body.project_id', 'proj-1')
  })

  it('allows user to change project in create mode', async () => {
    const user = userEvent.setup()
    render(<CredentialFormModal isOpen onClose={vi.fn()} defaultProjectId="proj-1" />, { wrapper })

    await user.click(screen.getByRole('button', { name: 'Credential project' }))
    await user.click(screen.getByRole('option', { name: 'Project Beta' }))
    await user.type(screen.getByLabelText('Credential name'), 'New Token')
    // type-1 (HTTP Bearer Token) is auto-selected
    await user.type(screen.getByLabelText('Token', { selector: 'input' }), 'my-secret-token')
    await user.click(screen.getByRole('button', { name: 'Create credential' }))

    await waitFor(() => expect(mockMutate).toHaveBeenCalled())
    // eslint-disable-next-line @typescript-eslint/no-unsafe-assignment
    const callArgs = mockMutate.mock.calls[0][0]
    expect(callArgs).toHaveProperty('body.project_id', 'proj-2')
  })

  it('disables project dropdown in edit mode', () => {
    render(<CredentialFormModal isOpen onClose={vi.fn()} credentialToEdit={mockCredential} />, { wrapper })

    expect(screen.getByLabelText('Credential project')).toBeDisabled()
  })

  it('shows credential project in edit mode', () => {
    render(<CredentialFormModal isOpen onClose={vi.fn()} credentialToEdit={mockCredential} />, { wrapper })

    expect(screen.getByRole('button', { name: 'Credential project' })).toHaveTextContent('Project Alpha')
  })

  it('shows loading state for projects', () => {
    const loadingMock = { projects: [], isLoading: true, error: null, refetch: vi.fn() }
    // eslint-disable-next-line @typescript-eslint/no-unsafe-argument, @typescript-eslint/no-explicit-any
    vi.mocked(useSelectableProjects).mockReturnValue(loadingMock as any)

    render(<CredentialFormModal isOpen onClose={vi.fn()} />, { wrapper })

    expect(screen.getByText('Loading projects...')).toBeInTheDocument()
    expect(screen.getByLabelText('Credential project')).toBeDisabled()
  })

  it('shows error when projects fail to load', () => {
    const errorMock = { projects: [], isLoading: false, error: new Error('Network error'), refetch: vi.fn() }
    // eslint-disable-next-line @typescript-eslint/no-unsafe-argument, @typescript-eslint/no-explicit-any
    vi.mocked(useSelectableProjects).mockReturnValue(errorMock as any)

    render(<CredentialFormModal isOpen onClose={vi.fn()} />, { wrapper })

    expect(screen.getByText('Failed to load projects')).toBeInTheDocument()
  })

  it('calls onCreated with the new credential ID on successful create', async () => {
    const onCreated = vi.fn()
    const onClose = vi.fn()
    mockMutate.mockImplementation((_args: unknown, callbacks: { onSuccess: (data: unknown) => void }) => {
      callbacks.onSuccess({ id: 'new-cred-123', name: 'New Token' })
    })

    const user = userEvent.setup()
    render(<CredentialFormModal isOpen onClose={onClose} onCreated={onCreated} defaultProjectId="proj-1" />, {
      wrapper,
    })

    await user.type(screen.getByLabelText('Credential name'), 'New Token')
    // type-1 (HTTP Bearer Token) is auto-selected
    await user.type(screen.getByLabelText('Token', { selector: 'input' }), 'secret')
    await user.click(screen.getByRole('button', { name: 'Create credential' }))

    await waitFor(() => expect(onCreated).toHaveBeenCalledWith('new-cred-123'))
    expect(onClose).toHaveBeenCalled()
  })

  describe('mutually exclusive field groups', () => {
    async function selectAAPType(user: ReturnType<typeof userEvent.setup>) {
      await user.click(screen.getByLabelText('Credential type'))
      await user.click(screen.getByRole('option', { name: 'Ansible Automation Platform' }))
    }

    async function selectAuthMethod(user: ReturnType<typeof userEvent.setup>, optionName: string) {
      await user.click(screen.getByLabelText('Auth method'))
      await user.click(screen.getByRole('option', { name: optionName }))
    }

    it('shows auth method dropdown for AAP credential type', async () => {
      const user = userEvent.setup()
      render(<CredentialFormModal isOpen onClose={vi.fn()} />, { wrapper })

      await selectAAPType(user)

      const authToggle = screen.getByLabelText('Auth method')
      expect(authToggle).toBeInTheDocument()
      expect(authToggle).toHaveTextContent('OAuth2 Token')
      await user.click(authToggle)
      expect(screen.getByRole('option', { name: 'OAuth2 Token' })).toBeInTheDocument()
      expect(screen.getByRole('option', { name: 'Basic Auth' })).toBeInTheDocument()
    })

    it('does not show auth method dropdown for types without mutually_exclusive', () => {
      render(<CredentialFormModal isOpen onClose={vi.fn()} />, { wrapper })

      expect(screen.queryByLabelText('Auth method')).not.toBeInTheDocument()
    })

    it('shows only OAuth Token fields by default (first group selected)', async () => {
      const user = userEvent.setup()
      render(<CredentialFormModal isOpen onClose={vi.fn()} />, { wrapper })

      await selectAAPType(user)

      expect(screen.getByLabelText('OAuth Token', { selector: 'input' })).toBeInTheDocument()
      expect(screen.queryByLabelText('Username', { selector: 'input' })).not.toBeInTheDocument()
      expect(screen.queryByLabelText('Password', { selector: 'input' })).not.toBeInTheDocument()
    })

    it('shows Username + Password fields when Basic Auth selected', async () => {
      const user = userEvent.setup()
      render(<CredentialFormModal isOpen onClose={vi.fn()} />, { wrapper })

      await selectAAPType(user)
      await selectAuthMethod(user, 'Basic Auth')

      expect(screen.getByLabelText('Username', { selector: 'input' })).toBeInTheDocument()
      expect(screen.getByLabelText('Password', { selector: 'input' })).toBeInTheDocument()
      expect(screen.queryByLabelText('OAuth Token', { selector: 'input' })).not.toBeInTheDocument()
    })

    it('clears hidden group values when switching groups', async () => {
      const user = userEvent.setup()
      render(<CredentialFormModal isOpen onClose={vi.fn()} />, { wrapper })

      await selectAAPType(user)
      // Fill OAuth Token
      await user.type(screen.getByLabelText('OAuth Token', { selector: 'input' }), 'my-token')
      // Switch to Basic Auth
      await selectAuthMethod(user, 'Basic Auth')
      // Switch back to OAuth2 Token
      await selectAuthMethod(user, 'OAuth2 Token')

      // Value should be cleared
      expect(screen.getByLabelText('OAuth Token', { selector: 'input' })).toHaveValue('')
    })

    it('pre-selects correct auth method in edit mode based on existing values', () => {
      const aapCredential = {
        id: 'cred-aap',
        name: 'My AAP',
        description: '',
        credential_type_id: 'type-aap',
        inputs: { username: 'admin', password: '$encrypted$' },
        enabled: true,
        labels: {},
        created_by: { id: '550e8400-e29b-41d4-a716-446655440001', name: 'user-1' },
        project_id: 'proj-1',
        created_at: '2026-03-01T00:00:00Z',
        updated_at: '2026-03-01T00:00:00Z',
      } as const

      render(<CredentialFormModal isOpen onClose={vi.fn()} credentialToEdit={aapCredential} />, { wrapper })

      // Basic Auth should be selected — the toggle displays the active group label
      expect(screen.getByLabelText('Auth method')).toHaveTextContent('Basic Auth')
      expect(screen.getByLabelText('Username', { selector: 'input' })).toBeInTheDocument()
      expect(screen.queryByLabelText('OAuth Token', { selector: 'input' })).not.toBeInTheDocument()
    })

    it('validates required_together — shows error when username is filled but password is not', async () => {
      const user = userEvent.setup()
      render(<CredentialFormModal isOpen onClose={vi.fn()} defaultProjectId="proj-1" />, { wrapper })

      await selectAAPType(user)
      await selectAuthMethod(user, 'Basic Auth')
      await user.type(screen.getByLabelText('Credential name'), 'Test AAP')
      await user.type(screen.getByLabelText('Username', { selector: 'input' }), 'admin')
      await user.click(screen.getByRole('button', { name: 'Create credential' }))

      expect(screen.getByText('Password is required')).toBeInTheDocument()
    })

    it('has no accessibility violations with auth method dropdown', async () => {
      const user = userEvent.setup()
      const { container } = render(<CredentialFormModal isOpen onClose={vi.fn()} />, { wrapper })

      await selectAAPType(user)

      expect(await axe(container)).toHaveNoViolations()
    })
  })
})
