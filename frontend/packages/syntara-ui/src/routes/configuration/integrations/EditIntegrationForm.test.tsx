import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { integrationsClient } from '../../../client'
import { AlertProvider } from '../../../providers/alerts'

import { EditIntegrationForm } from './EditIntegrationForm'

vi.mock('../../../client', () => ({
  integrationsClient: {
    useQuery: vi.fn(),
    useMutation: vi.fn(() => ({
      mutate: vi.fn(),
      mutateAsync: vi.fn().mockResolvedValue({}),
      isPending: false,
      isError: false,
    })),
  },
  credentialsClient: {
    useQuery: vi.fn(() => ({ data: undefined, isPending: false, isError: false, error: null })),
  },
}))

vi.mock('../../access/useAllProjects', () => {
  const projectsMock = () => ({
    projects: [
      { id: 'p-001', name: 'default' },
      { id: 'p-002', name: 'alice-sandbox' },
    ],
    isLoading: false,
    error: null,
    refetch: vi.fn(),
  })
  return { useAllProjects: projectsMock, useSelectableProjects: projectsMock }
})

const mockSyncAssignments = vi.fn().mockResolvedValue({ added: [], removed: [], errors: [] })
vi.mock('./useProjectAssignmentSync', () => ({
  useProjectAssignmentSync: () => ({ syncAssignments: mockSyncAssignments }),
}))

const mockNavigate = vi.fn()

vi.mock('@tanstack/react-router', async () => {
  const actual = await vi.importActual('@tanstack/react-router')
  const { MockLink } = await import('../../../test/setup')
  return {
    ...actual,
    Link: MockLink,
    useNavigate: () => mockNavigate,
    useParams: vi.fn(() => ({ integrationId: 'int-1' })),
  }
})

vi.mock('../../builder/components/CredentialSelector', () => ({
  CredentialSelector: ({
    label,
    fieldId,
    onChange,
    value,
  }: {
    label?: string
    fieldId?: string
    onChange?: (id: string | undefined) => void
    value?: string
  }) => (
    <div data-testid="credential-selector" aria-label={label}>
      <input id={fieldId} aria-label={label} readOnly value={value ?? ''} />
      <button data-testid="select-credential" onClick={() => onChange?.('cred-123')}>
        Select credential
      </button>
      <button data-testid="clear-credential" onClick={() => onChange?.(undefined)}>
        Clear credential
      </button>
    </div>
  ),
}))

const mockIntegration = {
  id: 'int-1',
  name: 'My MCP Server',
  description: 'A production integration',
  integration_type: 'mcp_server',
  enabled: true,
  validation_status: 'available',
  scope: 'global',
  configuration: {
    integration_type: 'mcp_server',
    base_url: 'https://mcp.example.com',
    allow_http: false,
    insecure_skip_tls_verify: false,
    ca_certificate: null,
  },
  management_credential_id: null,
  last_validated_at: '2026-01-01T00:00:00Z',
  validation_error: null,
  refresh_status: 'available',
  last_refreshed_at: '2026-01-01T00:00:00Z',
  refresh_error: null,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
  created_by: { id: 'a1b2c3d4-e5f6-7890-abcd-ef1234567890', name: 'user-1' },
  labels: {},
}

const mockAapIntegration = {
  id: 'int-2',
  name: 'My Ansible Automation Integration',
  description: 'A production Ansible Automation Platform',
  integration_type: 'ansible_automation_platform',
  enabled: true,
  validation_status: 'available',
  scope: 'global',
  configuration: {
    integration_type: 'ansible_automation_platform',
    base_url: 'https://aap.example.com',
    allow_http: false,
    insecure_skip_tls_verify: false,
    ca_certificate: null,
  },
  management_credential_id: null,
  last_validated_at: '2026-01-01T00:00:00Z',
  validation_error: null,
  refresh_status: 'available',
  last_refreshed_at: '2026-01-01T00:00:00Z',
  refresh_error: null,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
  created_by: { id: 'a1b2c3d4-e5f6-7890-abcd-ef1234567890', name: 'user-1' },
  labels: {},
}

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
})

const wrapper = ({ children }: { children: ReactNode }) => (
  <QueryClientProvider client={queryClient}>
    <AlertProvider>{children}</AlertProvider>
  </QueryClientProvider>
)

type MutationCallbacks = {
  onSuccess?: (result: unknown) => void
  onError?: (error: unknown) => void
}

function setupMocks(overrides?: {
  integration?: Record<string, unknown>
  isPending?: boolean
  isError?: boolean
  projectAssignments?: { resources: { project_id: string; project_name: string }[] }
}) {
  const integration = overrides?.integration ? { ...mockIntegration, ...overrides.integration } : mockIntegration

  vi.mocked(integrationsClient.useQuery).mockImplementation((_method: string, path: string) => {
    if (path === '/integrations/{integration_id}/projects') {
      return {
        data: overrides?.projectAssignments ?? { resources: [] },
        isPending: false,
        isError: false,
        error: null,
        refetch: vi.fn(),
      } as never
    }
    return {
      data: overrides?.isError ? undefined : integration,
      isPending: overrides?.isPending ?? false,
      isError: overrides?.isError ?? false,
      error: overrides?.isError ? new Error('Load failed') : null,
      refetch: vi.fn(),
    } as never
  })
}

function setupMutationMocks(patchMutateAsync?: ReturnType<typeof vi.fn>, discoverMutate?: ReturnType<typeof vi.fn>) {
  const patchAsync = patchMutateAsync ?? vi.fn().mockResolvedValue({})
  const discover = discoverMutate ?? vi.fn()
  vi.mocked(integrationsClient.useMutation).mockImplementation((_method: string, path: string) => {
    if (path === '/integrations/discover') {
      return { mutate: discover, mutateAsync: discover, isPending: false, isError: false } as never
    }
    return { mutate: vi.fn(), mutateAsync: patchAsync, isPending: false, isError: false } as never
  })
  return { patchMutate: patchAsync, discoverMutate: discover }
}

describe('EditIntegrationForm', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    setupMocks()
    setupMutationMocks()
  })

  describe('Rendering', () => {
    it('renders the page header with title and breadcrumbs', () => {
      render(<EditIntegrationForm />, { wrapper })

      expect(screen.getByRole('heading', { name: 'Edit integration' })).toBeInTheDocument()
      expect(screen.getByRole('navigation', { name: /breadcrumb/i })).toBeInTheDocument()
    })

    it('shows integration type as read-only text', () => {
      render(<EditIntegrationForm />, { wrapper })

      expect(screen.getByText('MCP Server')).toBeInTheDocument()
    })

    it('shows loading state while data loads', () => {
      setupMocks({ isPending: true })
      render(<EditIntegrationForm />, { wrapper })

      expect(screen.getByRole('heading', { name: 'Edit integration' })).toBeInTheDocument()
    })

    it('shows error state when loading fails', () => {
      setupMocks({ isError: true })
      render(<EditIntegrationForm />, { wrapper })

      expect(screen.getAllByText('Error loading integration').length).toBeGreaterThanOrEqual(1)
    })
  })

  describe('Field population', () => {
    it('populates name field from integration data', () => {
      render(<EditIntegrationForm />, { wrapper })

      expect(screen.getByDisplayValue('My MCP Server')).toBeInTheDocument()
    })

    it('populates description field from integration data', () => {
      render(<EditIntegrationForm />, { wrapper })

      expect(screen.getByDisplayValue('A production integration')).toBeInTheDocument()
    })

    it('populates API URL field from integration data', () => {
      render(<EditIntegrationForm />, { wrapper })

      expect(screen.getByDisplayValue('https://mcp.example.com')).toBeInTheDocument()
    })
  })

  describe('Form editing', () => {
    it('allows editing the name field', async () => {
      const user = userEvent.setup()
      render(<EditIntegrationForm />, { wrapper })

      const nameInput = screen.getByDisplayValue('My MCP Server')
      await user.clear(nameInput)
      await user.type(nameInput, 'Updated Server')

      expect(nameInput).toHaveValue('Updated Server')
    })

    it('allows editing the description field', async () => {
      const user = userEvent.setup()
      render(<EditIntegrationForm />, { wrapper })

      const descInput = screen.getByDisplayValue('A production integration')
      await user.clear(descInput)
      await user.type(descInput, 'New description')

      expect(descInput).toHaveValue('New description')
    })

    it('allows editing the API URL field', async () => {
      const user = userEvent.setup()
      render(<EditIntegrationForm />, { wrapper })

      const urlInput = screen.getByDisplayValue('https://mcp.example.com')
      await user.clear(urlInput)
      await user.type(urlInput, 'https://new.example.com')

      expect(urlInput).toHaveValue('https://new.example.com')
    })

    it('shows scope switch toggled on for global integrations', () => {
      render(<EditIntegrationForm />, { wrapper })

      expect(screen.getByRole('switch', { name: /integration scope/i })).toBeChecked()
      expect(screen.getByText('Global')).toBeInTheDocument()
    })

    it('shows scope switch toggled off for project integrations', () => {
      setupMocks({ integration: { scope: 'project' } })
      render(<EditIntegrationForm />, { wrapper })

      expect(screen.getByRole('switch', { name: /integration scope/i })).not.toBeChecked()
    })

    it('shows global scope helper text', () => {
      render(<EditIntegrationForm />, { wrapper })

      expect(screen.getByText(/Global integrations are available to all projects/i)).toBeInTheDocument()
    })
  })

  describe('Validation', () => {
    it('shows error when name is empty on save', async () => {
      const user = userEvent.setup()
      render(<EditIntegrationForm />, { wrapper })

      const nameInput = screen.getByDisplayValue('My MCP Server')
      await user.clear(nameInput)
      await user.click(screen.getByRole('button', { name: 'Save integration' }))

      await waitFor(() => {
        expect(screen.getByText('Server name / ID is required')).toBeInTheDocument()
      })
    })

    it('shows error when URL is empty for MCP server', async () => {
      const user = userEvent.setup()
      render(<EditIntegrationForm />, { wrapper })

      const urlInput = screen.getByDisplayValue('https://mcp.example.com')
      await user.clear(urlInput)
      await user.click(screen.getByRole('button', { name: 'Save integration' }))

      await waitFor(() => {
        expect(screen.getByText(/api url is required/i)).toBeInTheDocument()
      })
    })

    it('shows error when URL is not a valid URL', async () => {
      const user = userEvent.setup()
      render(<EditIntegrationForm />, { wrapper })

      const urlInput = screen.getByDisplayValue('https://mcp.example.com')
      await user.clear(urlInput)
      await user.type(urlInput, 'not-a-url')
      await user.click(screen.getByRole('button', { name: 'Save integration' }))

      await waitFor(() => {
        expect(screen.getByText(/must be a valid url/i)).toBeInTheDocument()
      })
    })
  })

  describe('Form submission', () => {
    it('calls PATCH with correct body on save', async () => {
      const { patchMutate } = setupMutationMocks()
      const user = userEvent.setup()
      render(<EditIntegrationForm />, { wrapper })

      await user.click(screen.getByRole('button', { name: 'Save integration' }))

      await waitFor(() => {
        expect(patchMutate).toHaveBeenCalledWith(
          expect.objectContaining({
            params: { path: { integration_id: 'int-1' } },
            body: expect.objectContaining({
              name: 'My MCP Server',
              description: 'A production integration',
              scope: 'global',
              configuration: {
                integration_type: 'mcp_server',
                base_url: 'https://mcp.example.com',
                allow_http: false,
                insecure_skip_tls_verify: false,
                ca_certificate: null,
              },
            }) as Record<string, unknown>,
          })
        )
      })
    })

    it('navigates to detail page on successful save', async () => {
      setupMutationMocks()

      const user = userEvent.setup()
      render(<EditIntegrationForm />, { wrapper })

      await user.click(screen.getByRole('button', { name: 'Save integration' }))

      await waitFor(() => {
        expect(mockNavigate).toHaveBeenCalledWith({ to: '/configuration/integrations/int-1' })
      })
    })

    it('shows success alert on successful save', async () => {
      setupMutationMocks()

      const user = userEvent.setup()
      render(<EditIntegrationForm />, { wrapper })

      await user.click(screen.getByRole('button', { name: 'Save integration' }))

      await waitFor(() => {
        expect(screen.getByText('Integration updated')).toBeInTheDocument()
      })
    })

    it('includes credential ID in save body when credential is selected', async () => {
      const { patchMutate } = setupMutationMocks()
      const user = userEvent.setup()
      render(<EditIntegrationForm />, { wrapper })

      await user.click(screen.getByTestId('select-credential'))
      await user.click(screen.getByRole('button', { name: 'Save integration' }))

      await waitFor(() => {
        expect(patchMutate).toHaveBeenCalledWith(
          expect.objectContaining({
            body: expect.objectContaining({
              management_credential_id: 'cred-123',
            }) as Record<string, unknown>,
          })
        )
      })
    })
  })

  describe('Credential save scenarios', () => {
    it('saves with null credential when credential is cleared', async () => {
      setupMocks({ integration: { management_credential_id: 'cred-existing' } })
      const { patchMutate } = setupMutationMocks()
      const user = userEvent.setup()
      render(<EditIntegrationForm />, { wrapper })

      await user.click(screen.getByTestId('clear-credential'))
      await user.click(screen.getByRole('button', { name: 'Save integration' }))

      await waitFor(() => {
        expect(patchMutate).toHaveBeenCalledWith(
          expect.objectContaining({
            body: expect.objectContaining({
              management_credential_id: null,
            }) as Record<string, unknown>,
          })
        )
      })
    })

    it('saves with new credential when changed from existing', async () => {
      setupMocks({ integration: { management_credential_id: 'cred-old' } })
      const { patchMutate } = setupMutationMocks()
      const user = userEvent.setup()
      render(<EditIntegrationForm />, { wrapper })

      await user.click(screen.getByTestId('select-credential'))
      await user.click(screen.getByRole('button', { name: 'Save integration' }))

      await waitFor(() => {
        expect(patchMutate).toHaveBeenCalledWith(
          expect.objectContaining({
            body: expect.objectContaining({
              management_credential_id: 'cred-123',
            }) as Record<string, unknown>,
          })
        )
      })
    })

    it('enables test connection when integration has existing credential', async () => {
      setupMocks({ integration: { management_credential_id: 'cred-existing' } })
      render(<EditIntegrationForm />, { wrapper })

      await waitFor(() => {
        expect(screen.getByRole('button', { name: 'Test connection' })).not.toHaveAttribute('aria-disabled', 'true')
      })
    })

    it('saves existing credential when no changes made', async () => {
      setupMocks({ integration: { management_credential_id: 'cred-existing' } })
      const { patchMutate } = setupMutationMocks()
      const user = userEvent.setup()
      render(<EditIntegrationForm />, { wrapper })

      await user.click(screen.getByRole('button', { name: 'Save integration' }))

      await waitFor(() => {
        expect(patchMutate).toHaveBeenCalledWith(
          expect.objectContaining({
            body: expect.objectContaining({
              management_credential_id: 'cred-existing',
            }) as Record<string, unknown>,
          })
        )
      })
    })
  })

  describe('Cancel', () => {
    it('navigates to detail page when Cancel is clicked', async () => {
      const user = userEvent.setup()
      render(<EditIntegrationForm />, { wrapper })

      await user.click(screen.getByRole('button', { name: 'Cancel' }))

      expect(mockNavigate).toHaveBeenCalledWith({ to: '/configuration/integrations/int-1' })
    })
  })

  describe('Credential section', () => {
    it('renders credential selector', () => {
      render(<EditIntegrationForm />, { wrapper })

      expect(screen.getByTestId('credential-selector')).toBeInTheDocument()
    })

    it('renders credential section heading and MCP description', () => {
      render(<EditIntegrationForm />, { wrapper })

      expect(screen.getByText('Connection credential')).toBeInTheDocument()
      expect(screen.getByText(/credential is used for tool discovery/i)).toBeInTheDocument()
    })

    it('enables test connection button for MCP when no credential is selected', () => {
      render(<EditIntegrationForm />, { wrapper })

      expect(screen.getByRole('button', { name: 'Test connection' })).not.toHaveAttribute('aria-disabled', 'true')
    })

    it('renders required description for LLM Provider', () => {
      setupMocks({
        integration: {
          integration_type: 'llm_provider',
          configuration: {
            integration_type: 'llm_provider',
            provider_hint: 'red_hat_ai',
            base_url: 'https://api.redhat-ai.example.com',
          },
        },
      })
      render(<EditIntegrationForm />, { wrapper })

      expect(screen.getByText('Connection credential')).toBeInTheDocument()
      expect(screen.getByText(/credential is used to verify the connection/i)).toBeInTheDocument()
    })

    it('disables test connection button for LLM Provider when no credential is selected', () => {
      setupMocks({
        integration: {
          integration_type: 'llm_provider',
          management_credential_id: null,
          configuration: {
            integration_type: 'llm_provider',
            provider_hint: 'red_hat_ai',
            base_url: 'https://api.redhat-ai.example.com',
          },
        },
      })
      render(<EditIntegrationForm />, { wrapper })

      expect(screen.getByRole('button', { name: 'Test connection' })).toHaveAttribute('aria-disabled', 'true')
    })

    it('enables test connection button after selecting a credential', async () => {
      const user = userEvent.setup()
      render(<EditIntegrationForm />, { wrapper })

      await user.click(screen.getByTestId('select-credential'))

      await waitFor(() => {
        expect(screen.getByRole('button', { name: 'Test connection' })).not.toHaveAttribute('aria-disabled', 'true')
      })
    })
  })

  describe('Test connection', () => {
    it('calls discover endpoint when test connection is clicked', async () => {
      const { discoverMutate } = setupMutationMocks()
      const user = userEvent.setup()
      render(<EditIntegrationForm />, { wrapper })

      await user.click(screen.getByTestId('select-credential'))
      await user.click(screen.getByRole('button', { name: 'Test connection' }))

      expect(discoverMutate).toHaveBeenCalledWith(
        expect.objectContaining({
          body: expect.objectContaining({
            credential_id: 'cred-123',
            integration_type: 'mcp_server',
          }) as Record<string, unknown>,
        }),
        expect.any(Object)
      )
    })

    it('shows success alert when connection test succeeds with tools', async () => {
      const discoverMutate = vi.fn()
      discoverMutate.mockImplementation((_body: unknown, callbacks: MutationCallbacks) => {
        callbacks.onSuccess?.({
          success: true,
          discovered_tools: [{ name: 'tool1' }, { name: 'tool2' }],
        })
      })
      setupMutationMocks(undefined, discoverMutate)

      const user = userEvent.setup()
      render(<EditIntegrationForm />, { wrapper })

      await user.click(screen.getByTestId('select-credential'))
      await user.click(screen.getByRole('button', { name: 'Test connection' }))

      await waitFor(() => {
        expect(screen.getByText('Connection tested')).toBeInTheDocument()
        expect(screen.getByText('Successfully connected. Discovered 2 tools.')).toBeInTheDocument()
      })
    })

    it('shows failure alert when connection test returns success: false', async () => {
      const discoverMutate = vi.fn()
      discoverMutate.mockImplementation((_body: unknown, callbacks: MutationCallbacks) => {
        callbacks.onSuccess?.({
          success: false,
          error: 'Connection refused',
        })
      })
      setupMutationMocks(undefined, discoverMutate)

      const user = userEvent.setup()
      render(<EditIntegrationForm />, { wrapper })

      await user.click(screen.getByTestId('select-credential'))
      await user.click(screen.getByRole('button', { name: 'Test connection' }))

      await waitFor(() => {
        expect(screen.getByText('Connection failed')).toBeInTheDocument()
        expect(screen.getByText('Connection refused')).toBeInTheDocument()
      })
    })

    it('shows error alert when connection test request fails', async () => {
      const discoverMutate = vi.fn()
      discoverMutate.mockImplementation((_body: unknown, callbacks: MutationCallbacks) => {
        callbacks.onError?.(new Error('Network error'))
      })
      setupMutationMocks(undefined, discoverMutate)

      const user = userEvent.setup()
      render(<EditIntegrationForm />, { wrapper })

      await user.click(screen.getByTestId('select-credential'))
      await user.click(screen.getByRole('button', { name: 'Test connection' }))

      await waitFor(() => {
        expect(screen.getByText('Connection test failed')).toBeInTheDocument()
      })
    })
  })

  describe('Ansible Automation Platform', () => {
    beforeEach(() => {
      setupMocks({ integration: mockAapIntegration })
    })

    it('shows Ansible Automation Platform as integration type', () => {
      render(<EditIntegrationForm />, { wrapper })

      expect(screen.getByText('Ansible Automation Platform')).toBeInTheDocument()
    })

    it('renders AAP URL field', () => {
      render(<EditIntegrationForm />, { wrapper })

      expect(screen.getByDisplayValue('https://aap.example.com')).toBeInTheDocument()
    })

    it('does not render API URL field for Ansible Automation Platform', () => {
      render(<EditIntegrationForm />, { wrapper })

      expect(screen.queryByLabelText('API URL')).not.toBeInTheDocument()
    })

    it('renders security section', () => {
      render(<EditIntegrationForm />, { wrapper })

      expect(screen.getByText('Security')).toBeInTheDocument()
    })

    it('calls PATCH with Ansible Automation Platform configuration on save', async () => {
      const { patchMutate } = setupMutationMocks()
      const user = userEvent.setup()
      render(<EditIntegrationForm />, { wrapper })

      await user.click(screen.getByRole('button', { name: 'Save integration' }))

      await waitFor(() => {
        expect(patchMutate).toHaveBeenCalledWith(
          expect.objectContaining({
            body: expect.objectContaining({
              configuration: {
                integration_type: 'ansible_automation_platform',
                base_url: 'https://aap.example.com',
                allow_http: false,
                insecure_skip_tls_verify: false,
                ca_certificate: null,
              },
            }) as Record<string, unknown>,
          })
        )
      })
    })

    it('calls discover with Ansible Automation Platform configuration on test connection', async () => {
      const { discoverMutate } = setupMutationMocks()
      const user = userEvent.setup()
      render(<EditIntegrationForm />, { wrapper })

      await user.click(screen.getByTestId('select-credential'))
      await user.click(screen.getByRole('button', { name: 'Test connection' }))

      expect(discoverMutate).toHaveBeenCalledWith(
        expect.objectContaining({
          body: expect.objectContaining({
            integration_type: 'ansible_automation_platform',
            configuration: expect.objectContaining({
              integration_type: 'ansible_automation_platform',
              base_url: 'https://aap.example.com',
            }) as Record<string, unknown>,
          }) as Record<string, unknown>,
        }),
        expect.any(Object)
      )
    })

    it('shows AAP-specific credential description text', () => {
      render(<EditIntegrationForm />, { wrapper })

      expect(screen.getByText(/verify the connection to the Ansible Automation Platform/i)).toBeInTheDocument()
    })

    it('shows error when AAP URL is empty', async () => {
      const user = userEvent.setup()
      render(<EditIntegrationForm />, { wrapper })

      const aapUrlInput = screen.getByDisplayValue('https://aap.example.com')
      await user.clear(aapUrlInput)
      await user.click(screen.getByRole('button', { name: 'Save integration' }))

      await waitFor(() => {
        expect(screen.getByText(/api url is required/i)).toBeInTheDocument()
      })
    })

    it('shows error when AAP URL is not a valid HTTPS URL', async () => {
      const user = userEvent.setup()
      render(<EditIntegrationForm />, { wrapper })

      const aapUrlInput = screen.getByDisplayValue('https://aap.example.com')
      await user.clear(aapUrlInput)
      await user.type(aapUrlInput, 'not-a-url')
      await user.click(screen.getByRole('button', { name: 'Save integration' }))

      await waitFor(() => {
        expect(screen.getByText(/must be a valid url/i)).toBeInTheDocument()
      })
    })

    it('handles null AAP URL in configuration gracefully', () => {
      setupMocks({
        integration: {
          ...mockAapIntegration,
          configuration: {
            integration_type: 'ansible_automation_platform',
            base_url: null,
            allow_http: false,
            insecure_skip_tls_verify: false,
            ca_certificate: null,
          },
        },
      })
      render(<EditIntegrationForm />, { wrapper })

      expect(screen.getByRole('textbox', { name: /api url/i })).toHaveValue('')
    })
  })

  describe('Accessibility', () => {
    it('has no accessibility violations', async () => {
      const { container } = render(<EditIntegrationForm />, { wrapper })
      expect(await axe(container)).toHaveNoViolations()
    })
  })

  describe('LLM Provider editing', () => {
    const llmIntegration = {
      ...mockIntegration,
      name: 'My LLM Provider',
      description: 'An LLM integration',
      integration_type: 'llm_provider',
      configuration: {
        integration_type: 'llm_provider',
        provider_hint: 'red_hat_ai',
        base_url: 'https://api.redhat-ai.example.com',
        allow_http: false,
        insecure_skip_tls_verify: false,
        ca_certificate: null,
      },
    }

    it('shows provider type as read-only text for LLM provider', () => {
      setupMocks({ integration: llmIntegration })
      render(<EditIntegrationForm />, { wrapper })

      expect(screen.getByText('LLM Provider')).toBeInTheDocument()
      expect(screen.getByText('Red Hat AI')).toBeInTheDocument()
    })

    it('shows base URL field for LLM provider with red_hat_ai', () => {
      setupMocks({ integration: llmIntegration })
      render(<EditIntegrationForm />, { wrapper })

      expect(screen.getByDisplayValue('https://api.redhat-ai.example.com')).toBeInTheDocument()
    })

    it('shows error when URL is empty for red_hat_ai provider', async () => {
      setupMocks({ integration: llmIntegration })
      const user = userEvent.setup()
      render(<EditIntegrationForm />, { wrapper })

      const urlInput = screen.getByDisplayValue('https://api.redhat-ai.example.com')
      await user.clear(urlInput)
      await user.click(screen.getByRole('button', { name: 'Save integration' }))

      await waitFor(() => {
        expect(screen.getByText(/api url is required/i)).toBeInTheDocument()
      })
    })

    it('shows error when URL is empty for custom provider', async () => {
      setupMocks({
        integration: {
          ...llmIntegration,
          configuration: {
            integration_type: 'llm_provider',
            provider_hint: 'custom',
            base_url: 'https://custom.example.com',
          },
        },
      })
      const user = userEvent.setup()
      render(<EditIntegrationForm />, { wrapper })

      const urlInput = screen.getByDisplayValue('https://custom.example.com')
      await user.clear(urlInput)
      await user.click(screen.getByRole('button', { name: 'Save integration' }))

      await waitFor(() => {
        expect(screen.getByText(/api url is required/i)).toBeInTheDocument()
      })
    })

    it('hides base URL field for openai provider', () => {
      setupMocks({
        integration: {
          ...llmIntegration,
          configuration: {
            integration_type: 'llm_provider',
            provider_hint: 'openai',
          },
        },
      })
      render(<EditIntegrationForm />, { wrapper })

      expect(screen.queryByRole('textbox', { name: /api url/i })).not.toBeInTheDocument()
    })

    it('hides base URL field for anthropic provider', () => {
      setupMocks({
        integration: {
          ...llmIntegration,
          configuration: {
            integration_type: 'llm_provider',
            provider_hint: 'anthropic',
          },
        },
      })
      render(<EditIntegrationForm />, { wrapper })

      expect(screen.queryByRole('textbox', { name: /api url/i })).not.toBeInTheDocument()
    })

    it('sends correct LLM configuration in PATCH body', async () => {
      setupMocks({ integration: llmIntegration })
      const { patchMutate } = setupMutationMocks()
      const user = userEvent.setup()
      render(<EditIntegrationForm />, { wrapper })

      await user.click(screen.getByRole('button', { name: 'Save integration' }))

      await waitFor(() => {
        expect(patchMutate).toHaveBeenCalledWith(
          expect.objectContaining({
            body: expect.objectContaining({
              configuration: expect.objectContaining({
                integration_type: 'llm_provider',
                provider_hint: 'red_hat_ai',
              }) as Record<string, unknown>,
            }) as Record<string, unknown>,
          })
        )
      })
    })

    it('test connection shows models for LLM provider', async () => {
      setupMocks({ integration: { ...llmIntegration, management_credential_id: 'cred-existing' } })
      const discoverMutate = vi.fn()
      discoverMutate.mockImplementation((_body: unknown, callbacks: MutationCallbacks) => {
        callbacks.onSuccess?.({
          success: true,
          discovered_models: [
            { id: 'm1', name: 'model-1' },
            { id: 'm2', name: 'model-2' },
          ],
        })
      })
      setupMutationMocks(undefined, discoverMutate)

      const user = userEvent.setup()
      render(<EditIntegrationForm />, { wrapper })

      await user.click(screen.getByRole('button', { name: 'Test connection' }))

      await waitFor(() => {
        expect(screen.getByText('Successfully connected. Discovered 2 models.')).toBeInTheDocument()
      })
    })

    it('MCP edit flow still works unchanged (regression)', () => {
      render(<EditIntegrationForm />, { wrapper })

      expect(screen.getByText('MCP Server')).toBeInTheDocument()
      expect(screen.getByDisplayValue('https://mcp.example.com')).toBeInTheDocument()
    })
  })

  describe('Null configuration fallbacks', () => {
    it('handles null base_url in MCP configuration', () => {
      setupMocks({
        integration: {
          configuration: {
            integration_type: 'mcp_server',
            base_url: null,
          },
        },
      })
      render(<EditIntegrationForm />, { wrapper })

      const urlInput = screen.getByRole('textbox', { name: /api url/i })
      expect(urlInput).toHaveValue('')
    })

    it('handles missing integration_type with fallback', () => {
      setupMocks({
        integration: {
          integration_type: null,
          configuration: {
            integration_type: 'mcp_server',
            base_url: 'https://mcp.example.com',
          },
        },
      })
      render(<EditIntegrationForm />, { wrapper })

      expect(screen.getByDisplayValue('https://mcp.example.com')).toBeInTheDocument()
    })
  })

  describe('Project assignment sync on save', () => {
    beforeEach(() => {
      mockSyncAssignments.mockClear()
    })

    it('calls syncAssignments when saving a project-scoped integration', async () => {
      setupMocks({
        integration: { scope: 'project' },
        projectAssignments: {
          resources: [{ project_id: 'p-001', project_name: 'default' }],
        },
      })
      const { patchMutate } = setupMutationMocks()
      const user = userEvent.setup()
      render(<EditIntegrationForm />, { wrapper })

      await user.click(screen.getByRole('button', { name: 'Save integration' }))

      await waitFor(() => {
        expect(patchMutate).toHaveBeenCalled()
      })
      await waitFor(() => {
        expect(mockSyncAssignments).toHaveBeenCalledWith('int-1', ['p-001'], ['p-001'])
      })
    })

    it('shows warning alert when project sync has errors', async () => {
      mockSyncAssignments.mockResolvedValueOnce({ added: [], removed: [], errors: ['Failed'] })
      setupMocks({
        integration: { scope: 'project' },
        projectAssignments: {
          resources: [{ project_id: 'p-001', project_name: 'default' }],
        },
      })
      setupMutationMocks()
      const user = userEvent.setup()
      render(<EditIntegrationForm />, { wrapper })

      await user.click(screen.getByRole('button', { name: 'Save integration' }))

      await waitFor(() => {
        expect(screen.getByText('Integration updated with warnings')).toBeInTheDocument()
      })
    })

    it('does not call syncAssignments when scope is global', async () => {
      setupMocks({ integration: { scope: 'global' } })
      setupMutationMocks()
      const user = userEvent.setup()
      render(<EditIntegrationForm />, { wrapper })

      await user.click(screen.getByRole('button', { name: 'Save integration' }))

      await waitFor(() => {
        expect(screen.getByText('Integration updated')).toBeInTheDocument()
      })
      expect(mockSyncAssignments).not.toHaveBeenCalled()
    })

    it('shows project selector when scope is toggled to project', async () => {
      setupMocks({ integration: { scope: 'global' } })
      setupMutationMocks()
      const user = userEvent.setup()
      render(<EditIntegrationForm />, { wrapper })

      await user.click(screen.getByRole('switch', { name: /integration scope/i }))

      await waitFor(() => {
        expect(screen.getByText('Projects')).toBeInTheDocument()
      })
    })
  })

  describe('system-managed fields are not rendered as editable inputs', () => {
    it('does not render editable controls for system-managed fields', async () => {
      setupMocks({
        integration: {
          validation_status: 'available',
          last_validated_at: '2026-06-15T12:00:00Z',
          validation_error: null,
          refresh_status: 'available',
          last_refreshed_at: '2026-06-15T12:00:00Z',
        },
      })
      setupMutationMocks()
      const { container } = render(<EditIntegrationForm />, { wrapper })

      const systemFields = [
        'validation_status',
        'last_validated_at',
        'validation_error',
        'refresh_status',
        'last_refreshed_at',
        'refresh_error',
      ]
      for (const field of systemFields) {
        expect(screen.queryByRole('textbox', { name: new RegExp(field, 'i') })).not.toBeInTheDocument()
        expect(screen.queryByRole('combobox', { name: new RegExp(field, 'i') })).not.toBeInTheDocument()
      }

      expect(await axe(container)).toHaveNoViolations()
    })
  })
})
