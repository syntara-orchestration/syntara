import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactNode } from 'react'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { axe } from 'vitest-axe'

import { accessClient } from '../../access/accessClient'
import { useCredentialExpirationDate } from '../../access-management/service-accounts/useCredentialExpirationDate'

import {
  CreateServiceAccountInlineModal,
  CredentialRevealBody,
  ProjectSelectToggle,
} from './CreateServiceAccountInlineModal'
import { useCreateServiceAccountInline } from './useCreateServiceAccountInline'

const PROJECT_UUID = '00000000-0000-0000-0000-000000000001'

vi.mock('../../access/accessClient', () => ({
  accessClient: {
    useQuery: vi.fn(),
    useMutation: vi.fn(),
  },
}))

vi.mock('../../access/useAllProjects', () => ({
  useSelectableProjects: () => ({
    projects: [
      { id: PROJECT_UUID, name: 'Default' },
      { id: '00000000-0000-0000-0000-000000000002', name: 'Production' },
    ],
  }),
}))

vi.mock('../../../hooks/useFormMutationErrorHandler', () => ({
  useFormMutationErrorHandler: () => () => vi.fn(),
}))

vi.mock('../../access-management/service-accounts/useCredentialExpirationDate', () => ({
  useCredentialExpirationDate: vi.fn(() => ({
    value: '2026-12-31',
    error: '',
    handleChange: vi.fn(),
    validator: () => '',
    helperText: 'Maximum lifetime: 180 days',
    validate: vi.fn(() => true),
    reset: vi.fn(),
  })),
}))

vi.mock('../../access-management/service-accounts/CredentialExpirationField', () => ({
  CredentialExpirationField: () => <div data-testid="expiration-field">Expiration field</div>,
}))

vi.mock('../../../utils/dateUtils', () => ({
  formatExpirationDate: (d: string) => d,
  formatDateYMD: (d: Date) => d.toISOString().slice(0, 10),
  parseDateYMD: (s: string) => new Date(s),
}))

vi.mock('./useCreateServiceAccountInline', async (importOriginal) => {
  const actual = await importOriginal<typeof import('./useCreateServiceAccountInline')>()
  return { ...actual, useCreateServiceAccountInline: vi.fn(actual.useCreateServiceAccountInline) }
})

const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
const wrapper = ({ children }: { children: ReactNode }) => (
  <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
)

function setupMutationMocks() {
  vi.mocked(accessClient.useMutation).mockReturnValue({
    mutateAsync: vi.fn().mockResolvedValue({ id: 'new-sa', name: 'test' }),
    isPending: false,
  } as ReturnType<typeof accessClient.useMutation>)
}

describe('CreateServiceAccountInlineModal', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    queryClient.clear()
  })

  it('does not render when closed', () => {
    setupMutationMocks()
    render(<CreateServiceAccountInlineModal isOpen={false} onClose={vi.fn()} onCreated={vi.fn()} />, { wrapper })
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('renders create form with name, description, and project fields', () => {
    setupMutationMocks()
    render(<CreateServiceAccountInlineModal isOpen onClose={vi.fn()} onCreated={vi.fn()} />, { wrapper })
    expect(screen.getByRole('dialog')).toBeInTheDocument()
    expect(screen.getByRole('textbox', { name: 'Name' })).toBeInTheDocument()
    expect(screen.getByRole('textbox', { name: 'Description' })).toBeInTheDocument()
    expect(screen.getByText('Select a project')).toBeInTheDocument()
  })

  it('pre-selects project when projectId is provided', () => {
    setupMutationMocks()
    render(<CreateServiceAccountInlineModal isOpen onClose={vi.fn()} onCreated={vi.fn()} projectId={PROJECT_UUID} />, {
      wrapper,
    })
    expect(screen.getByText('Default')).toBeInTheDocument()
  })

  it('allows typing in name field', async () => {
    setupMutationMocks()
    const user = userEvent.setup()
    render(<CreateServiceAccountInlineModal isOpen onClose={vi.fn()} onCreated={vi.fn()} />, { wrapper })
    const nameField = screen.getByRole('textbox', { name: 'Name' })
    await user.type(nameField, 'my-new-sa')
    expect(nameField).toHaveValue('my-new-sa')
  })

  it('allows typing in description field', async () => {
    setupMutationMocks()
    const user = userEvent.setup()
    render(<CreateServiceAccountInlineModal isOpen onClose={vi.fn()} onCreated={vi.fn()} />, { wrapper })
    const descField = screen.getByRole('textbox', { name: 'Description' })
    await user.type(descField, 'Test description')
    expect(descField).toHaveValue('Test description')
  })

  it('shows create and cancel buttons', () => {
    setupMutationMocks()
    render(<CreateServiceAccountInlineModal isOpen onClose={vi.fn()} onCreated={vi.fn()} />, { wrapper })
    expect(screen.getByRole('button', { name: /create service account/i })).toBeInTheDocument()
    expect(screen.getByText('Cancel')).toBeInTheDocument()
  })

  it('calls onClose when cancel is clicked', async () => {
    setupMutationMocks()
    const resetExpirationDate = vi.fn()
    vi.mocked(useCredentialExpirationDate).mockReturnValue({
      value: '2026-12-31',
      error: '',
      handleChange: vi.fn(),
      validator: () => '',
      helperText: 'Maximum lifetime: 180 days',
      validate: vi.fn(() => true),
      reset: resetExpirationDate,
    })
    const onClose = vi.fn()
    const onCreated = vi.fn()
    const user = userEvent.setup()
    render(<CreateServiceAccountInlineModal isOpen onClose={onClose} onCreated={onCreated} />, { wrapper })
    await user.click(screen.getByText('Cancel'))
    expect(onClose).toHaveBeenCalled()
    expect(resetExpirationDate).toHaveBeenCalled()
    expect(onCreated).not.toHaveBeenCalled()
  })

  it('shows name validation helper text', () => {
    setupMutationMocks()
    render(<CreateServiceAccountInlineModal isOpen onClose={vi.fn()} onCreated={vi.fn()} />, { wrapper })
    expect(screen.getByText(/lowercase letters, numbers, and hyphens/i)).toBeInTheDocument()
  })

  it('renders credential expiration date field', () => {
    setupMutationMocks()
    render(<CreateServiceAccountInlineModal isOpen onClose={vi.fn()} onCreated={vi.fn()} />, { wrapper })
    expect(screen.getByTestId('expiration-field')).toBeInTheDocument()
  })

  it('renders project options in dropdown', async () => {
    setupMutationMocks()
    const user = userEvent.setup()
    render(<CreateServiceAccountInlineModal isOpen onClose={vi.fn()} onCreated={vi.fn()} />, { wrapper })
    await user.click(screen.getByText('Select a project'))
    expect(screen.getByText('Default')).toBeInTheDocument()
    expect(screen.getByText('Production')).toBeInTheDocument()
  })

  it('disables create button when isPending is true', () => {
    vi.mocked(accessClient.useMutation).mockReturnValue({
      mutateAsync: vi.fn(),
      isPending: true,
    } as ReturnType<typeof accessClient.useMutation>)

    render(<CreateServiceAccountInlineModal isOpen onClose={vi.fn()} onCreated={vi.fn()} />, { wrapper })

    expect(screen.getByRole('button', { name: /create service account/i })).toBeDisabled()
    expect(screen.getByText('Cancel')).toBeInTheDocument()
  })

  it('stays enabled when expirationError is set and validates on click', async () => {
    setupMutationMocks()
    const validate = vi.fn(() => false)
    const mutateAsync = vi.fn()
    vi.mocked(accessClient.useMutation).mockReturnValue({
      mutateAsync,
      isPending: false,
    } as ReturnType<typeof accessClient.useMutation>)
    vi.mocked(useCredentialExpirationDate).mockReturnValue({
      value: '2020-01-01',
      error: 'Date must be in the future',
      handleChange: vi.fn(),
      validator: () => 'Date must be in the future',
      helperText: 'Maximum lifetime: 180 days',
      validate,
      reset: vi.fn(),
    })

    const user = userEvent.setup()
    render(<CreateServiceAccountInlineModal isOpen onClose={vi.fn()} onCreated={vi.fn()} />, { wrapper })

    const createButton = screen.getByRole('button', { name: /create service account/i })
    expect(createButton).toBeEnabled()

    await user.click(createButton)

    expect(validate).toHaveBeenCalled()
    expect(mutateAsync).not.toHaveBeenCalled()
  })

  it('disables cancel button when isPending is true', () => {
    vi.mocked(accessClient.useMutation).mockReturnValue({
      mutateAsync: vi.fn(),
      isPending: true,
    } as ReturnType<typeof accessClient.useMutation>)

    render(<CreateServiceAccountInlineModal isOpen onClose={vi.fn()} onCreated={vi.fn()} />, { wrapper })

    expect(screen.getByRole('button', { name: 'Cancel' })).toBeDisabled()
  })

  it('does not call onCreated when closing without a created SA', async () => {
    setupMutationMocks()
    const user = userEvent.setup()
    const onClose = vi.fn()
    const onCreated = vi.fn()

    render(<CreateServiceAccountInlineModal isOpen onClose={onClose} onCreated={onCreated} />, { wrapper })

    await user.click(screen.getByText('Cancel'))

    expect(onClose).toHaveBeenCalled()
    expect(onCreated).not.toHaveBeenCalled()
  })

  it('has no accessibility violations when open', async () => {
    setupMutationMocks()
    const { container } = render(<CreateServiceAccountInlineModal isOpen onClose={vi.fn()} onCreated={vi.fn()} />, {
      wrapper,
    })
    expect(await axe(container)).toHaveNoViolations()
  })
})

describe('CredentialRevealBody', () => {
  it('renders client ID and secret labels', () => {
    render(<CredentialRevealBody credentials={{ identifier: 'nx_sa_test', client_secret: 'my-secret' }} />)

    expect(screen.getByText('Client ID')).toBeInTheDocument()
    expect(screen.getByText('Client secret')).toBeInTheDocument()
  })

  it('shows save warning alert', () => {
    render(<CredentialRevealBody credentials={{ identifier: 'id', client_secret: 'sec' }} />)

    expect(screen.getByText(/will not be shown again/)).toBeInTheDocument()
  })

  it('shows next step info alert', () => {
    render(<CredentialRevealBody credentials={{ identifier: 'id', client_secret: 'sec' }} />)

    expect(screen.getByText(/Assign roles to this service account later/)).toBeInTheDocument()
  })

  it('shows expiration date when provided', () => {
    render(
      <CredentialRevealBody
        credentials={{ identifier: 'id', client_secret: 'sec', expiresAt: '2026-12-31T00:00:00Z' }}
      />
    )
    expect(screen.getByText('Expires')).toBeInTheDocument()
  })

  it('does not show expiration when not provided', () => {
    render(<CredentialRevealBody credentials={{ identifier: 'id', client_secret: 'sec' }} />)
    expect(screen.queryByText('Expires')).not.toBeInTheDocument()
  })

  it('has no accessibility violations', async () => {
    const { container } = render(
      <CredentialRevealBody credentials={{ identifier: 'nx_sa_test', client_secret: 'secret' }} />
    )
    expect(await axe(container)).toHaveNoViolations()
  })
})

describe('ProjectSelectToggle', () => {
  it('renders label text', () => {
    render(<ProjectSelectToggle toggleRef={null} label="Default" isOpen={false} onToggle={vi.fn()} />)

    expect(screen.getByText('Default')).toBeInTheDocument()
  })

  it('calls onToggle when clicked', async () => {
    const onToggle = vi.fn()
    const user = userEvent.setup()
    render(<ProjectSelectToggle toggleRef={null} label="Select" isOpen={false} onToggle={onToggle} />)

    await user.click(screen.getByText('Select'))
    expect(onToggle).toHaveBeenCalled()
  })
})

describe('CreateServiceAccountInlineModal — Credential Reveal', () => {
  const mockSetSavedAck = vi.fn()
  const mockResetState = vi.fn()

  beforeEach(() => {
    vi.clearAllMocks()
    queryClient.clear()
  })

  function setupCredentialRevealState(overrides?: { savedAck?: boolean }) {
    setupMutationMocks()
    vi.mocked(useCreateServiceAccountInline).mockReturnValue({
      credentials: { identifier: 'nx_sa_test', client_secret: 'secret123', expiresAt: '2026-12-31T00:00:00Z' },
      createdSaId: 'new-sa-id',
      savedAck: overrides?.savedAck ?? false,
      setSavedAck: mockSetSavedAck,
      isPending: false,
      submitForm: vi.fn(),
      resetState: mockResetState.mockReturnValue('new-sa-id'),
      showCredentials: true,
    })
  }

  it('shows credential reveal title and credential fields', () => {
    setupCredentialRevealState()

    render(<CreateServiceAccountInlineModal isOpen onClose={vi.fn()} onCreated={vi.fn()} projectId={PROJECT_UUID} />, {
      wrapper,
    })

    expect(screen.getByText('Service account created')).toBeInTheDocument()
    expect(screen.getByText('Client ID')).toBeInTheDocument()
    expect(screen.getByText('Client secret')).toBeInTheDocument()
    expect(screen.getByText(/will not be shown again/)).toBeInTheDocument()
  })

  it('shows savedAck checkbox', () => {
    setupCredentialRevealState()

    render(<CreateServiceAccountInlineModal isOpen onClose={vi.fn()} onCreated={vi.fn()} projectId={PROJECT_UUID} />, {
      wrapper,
    })

    expect(screen.getByLabelText('I have saved the credentials')).toBeInTheDocument()
  })

  function getFooterCloseButton() {
    const buttons = screen.getAllByRole('button', { name: 'Close' })
    return buttons[buttons.length - 1]
  }

  it('disables Close button when savedAck is unchecked', () => {
    setupCredentialRevealState({ savedAck: false })

    render(<CreateServiceAccountInlineModal isOpen onClose={vi.fn()} onCreated={vi.fn()} projectId={PROJECT_UUID} />, {
      wrapper,
    })

    expect(getFooterCloseButton()).toBeDisabled()
  })

  it('enables Close button when savedAck is checked', () => {
    setupCredentialRevealState({ savedAck: true })

    render(<CreateServiceAccountInlineModal isOpen onClose={vi.fn()} onCreated={vi.fn()} projectId={PROJECT_UUID} />, {
      wrapper,
    })

    expect(getFooterCloseButton()).toBeEnabled()
  })

  it('calls onCreated with SA id when closing after creation', async () => {
    setupCredentialRevealState({ savedAck: true })
    const user = userEvent.setup()
    const onClose = vi.fn()
    const onCreated = vi.fn()

    render(
      <CreateServiceAccountInlineModal isOpen onClose={onClose} onCreated={onCreated} projectId={PROJECT_UUID} />,
      { wrapper }
    )

    await user.click(getFooterCloseButton())

    expect(mockResetState).toHaveBeenCalled()
    expect(onClose).toHaveBeenCalled()
    expect(onCreated).toHaveBeenCalledWith('new-sa-id')
  })

  it('hides create/cancel buttons in credential reveal mode', () => {
    setupCredentialRevealState()

    render(<CreateServiceAccountInlineModal isOpen onClose={vi.fn()} onCreated={vi.fn()} projectId={PROJECT_UUID} />, {
      wrapper,
    })

    expect(screen.queryByRole('button', { name: /create service account/i })).not.toBeInTheDocument()
    expect(screen.queryByText('Cancel')).not.toBeInTheDocument()
  })

  it('has no accessibility violations in credential reveal mode', async () => {
    setupCredentialRevealState()

    const { container } = render(
      <CreateServiceAccountInlineModal isOpen onClose={vi.fn()} onCreated={vi.fn()} projectId={PROJECT_UUID} />,
      { wrapper }
    )

    expect(await axe(container)).toHaveNoViolations()
  })
})
