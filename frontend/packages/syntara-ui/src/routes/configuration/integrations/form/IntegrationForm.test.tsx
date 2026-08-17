import { IntegrationTypeEnum } from '@syntara/contracts'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactNode } from 'react'
import { type Mock, beforeEach, describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { tanstackRouter } from '../../../../app/tanstackRouter'
import { integrationsClient } from '../../../../client'
import { AlertProvider } from '../../../../providers/alerts'
import type { DocKey } from '../../../../utils/docs/types'

import { IntegrationForm } from './IntegrationForm'

const useDocLinkMock = vi.fn((key: DocKey) => `https://docs.example/${key}`)

vi.mock('../../../../utils/docs/useDocLink', () => ({
  useDocLink: (key: DocKey) => useDocLinkMock(key),
}))

vi.mock('../useProjectAssignmentSync', () => ({
  useProjectAssignmentSync: () => ({
    syncAssignments: vi.fn().mockResolvedValue({ added: [], removed: [], errors: [] }),
  }),
}))

vi.mock('../../../../client', () => ({
  integrationsClient: {
    useMutation: vi.fn(() => ({
      mutate: vi.fn(),
      mutateAsync: vi.fn().mockResolvedValue({ id: 'new-id' }),
      isPending: false,
      isError: false,
    })),
  },
  credentialsClient: {
    useQuery: vi.fn(() => ({ data: { results: [] }, isLoading: false, error: null, refetch: vi.fn() })),
  },
}))

vi.mock('../../../../app/tanstackRouter', () => ({
  tanstackRouter: { navigate: vi.fn().mockResolvedValue(undefined) },
}))

vi.mock('../../../access/useAllProjects', () => {
  const projectsMock = vi.fn(() => ({ projects: [], isLoading: false, error: null, refetch: vi.fn() }))
  return { useAllProjects: projectsMock, useSelectableProjects: projectsMock }
})

vi.mock('../../../builder/components/CredentialSelector', () => ({
  CredentialSelector: ({
    label,
    fieldId,
    onChange,
  }: {
    label?: string
    fieldId?: string
    onChange?: (id: string | undefined) => void
  }) => (
    <div data-testid="credential-selector" aria-label={label}>
      <input id={fieldId} aria-label={label} />
      <button data-testid="select-credential" onClick={() => onChange?.('cred-123')}>
        Select credential
      </button>
      <button data-testid="clear-credential" onClick={() => onChange?.(undefined)}>
        Clear credential
      </button>
    </div>
  ),
}))

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
})

const wrapper = ({ children }: { children: ReactNode }) => (
  <QueryClientProvider client={queryClient}>
    <AlertProvider>{children}</AlertProvider>
  </QueryClientProvider>
)

function advanceToStep2(user: ReturnType<typeof userEvent.setup>) {
  return async () => {
    await user.type(screen.getByRole('textbox', { name: /name/i }), 'Test MCP')
    await user.type(screen.getByRole('textbox', { name: /api url/i }), 'http://localhost:8765/mcp')
    await user.click(screen.getByRole('button', { name: 'Next' }))
  }
}

type MutationCallbacks = {
  onSuccess?: (result: unknown) => void
  onError?: (error: unknown) => void
}

function mockMutations(discoverMutate?: Mock, createMutate?: Mock) {
  const discoverFn = discoverMutate ?? vi.fn()
  const createFn = createMutate ?? vi.fn()
  const createAsyncFn = vi.fn().mockResolvedValue({ id: 'new-id', name: 'Test' })
  vi.mocked(integrationsClient.useMutation).mockImplementation((_method: string, path: string) => {
    if (path === '/integrations/discover') {
      return { mutate: discoverFn, mutateAsync: discoverFn, isPending: false, isError: false } as never
    }
    return { mutate: createFn, mutateAsync: createAsyncFn, isPending: false, isError: false } as never
  })
  return { discoverMutate: discoverFn, createMutate: createFn, createAsyncMutate: createAsyncFn }
}

describe('IntegrationForm', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('uses configureIntegration documentation key', () => {
    render(<IntegrationForm />, { wrapper })

    expect(useDocLinkMock).toHaveBeenCalledWith('configureIntegration')
    expect(screen.getByRole('link', { name: /documentation/i })).toHaveAttribute(
      'href',
      'https://docs.example/configureIntegration'
    )
  })

  it('renders the wizard with three steps in navigation', () => {
    render(<IntegrationForm />, { wrapper })

    const nav = screen.getByRole('navigation', { name: /wizard/i })
    expect(nav).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Integration details/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Connection credential/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Enable tools/i })).toBeInTheDocument()
  })

  it('shows step 1 fields by default', () => {
    render(<IntegrationForm />, { wrapper })

    expect(screen.getByText('MCP Server')).toBeInTheDocument()
    expect(screen.getByRole('textbox', { name: /name/i })).toBeInTheDocument()
    expect(screen.getByRole('textbox', { name: /description/i })).toBeInTheDocument()
    expect(screen.getByRole('textbox', { name: /api url/i })).toBeInTheDocument()
  })

  it('shows MCP Server as selected integration type', () => {
    render(<IntegrationForm />, { wrapper })

    expect(screen.getByText('MCP Server')).toBeInTheDocument()
  })

  it('shows Next and Cancel buttons on step 1', () => {
    render(<IntegrationForm />, { wrapper })

    expect(screen.getByRole('button', { name: 'Next' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Back' })).not.toBeInTheDocument()
  })

  it('validates required fields before advancing to step 2', async () => {
    const user = userEvent.setup()
    render(<IntegrationForm />, { wrapper })

    await user.click(screen.getByRole('button', { name: 'Next' }))

    expect(screen.getByText('Server name / ID is required')).toBeInTheDocument()
    expect(screen.getByText('API URL is required')).toBeInTheDocument()
  })

  it('advances to step 2 when required fields are filled', async () => {
    const user = userEvent.setup()
    render(<IntegrationForm />, { wrapper })

    await user.type(screen.getByRole('textbox', { name: /name/i }), 'Test MCP')
    await user.type(screen.getByRole('textbox', { name: /api url/i }), 'http://localhost:8765/mcp')
    await user.click(screen.getByRole('button', { name: 'Next' }))

    expect(screen.getByText(/credential is used to discover/i)).toBeInTheDocument()
    expect(screen.getByTestId('credential-selector')).toBeInTheDocument()
  })

  it('shows Back button on step 2', async () => {
    const user = userEvent.setup()
    render(<IntegrationForm />, { wrapper })

    await user.type(screen.getByRole('textbox', { name: /name/i }), 'Test MCP')
    await user.type(screen.getByRole('textbox', { name: /api url/i }), 'http://localhost:8765/mcp')
    await user.click(screen.getByRole('button', { name: 'Next' }))

    expect(screen.getByRole('button', { name: 'Back' })).toBeInTheDocument()
  })

  it('renders the page header with breadcrumbs', () => {
    render(<IntegrationForm />, { wrapper })

    expect(screen.getByRole('heading', { name: 'Configure integration' })).toBeInTheDocument()
    expect(screen.getByRole('navigation', { name: /breadcrumb/i })).toBeInTheDocument()
  })

  it('allows users to fill out all form fields', async () => {
    const user = userEvent.setup()
    render(<IntegrationForm />, { wrapper })

    const nameInput = screen.getByRole('textbox', { name: /name/i })
    const descriptionInput = screen.getByRole('textbox', { name: /description/i })
    const baseUrlInput = screen.getByRole('textbox', { name: /api url/i })

    await user.type(nameInput, 'My MCP Server')
    await user.type(descriptionInput, 'A test integration')
    await user.type(baseUrlInput, 'http://localhost:8765/mcp')

    expect(nameInput).toHaveValue('My MCP Server')
    expect(descriptionInput).toHaveValue('A test integration')
    expect(baseUrlInput).toHaveValue('http://localhost:8765/mcp')
  })

  it('does not advance when API URL is invalid', async () => {
    const user = userEvent.setup()
    render(<IntegrationForm />, { wrapper })

    await user.type(screen.getByRole('textbox', { name: /name/i }), 'Test MCP')
    await user.type(screen.getByRole('textbox', { name: /api url/i }), 'not-a-url')
    await user.click(screen.getByRole('button', { name: 'Next' }))

    expect(screen.getByText(/must be a valid url/i)).toBeInTheDocument()
    expect(screen.queryByText(/credential is used to discover/i)).not.toBeInTheDocument()
  })

  it('does not advance when MCP URL is non-loopback HTTP without allow_http', async () => {
    const user = userEvent.setup()
    render(<IntegrationForm />, { wrapper })

    await user.type(screen.getByRole('textbox', { name: /name/i }), 'Test MCP')
    await user.type(screen.getByRole('textbox', { name: /api url/i }), 'http://remote-server.example.com:8765/mcp')
    await user.click(screen.getByRole('button', { name: 'Next' }))

    expect(screen.queryByText(/credential is used to discover/i)).not.toBeInTheDocument()
    expect(screen.getByText('Must be an HTTPS URL')).toBeInTheDocument()
  })

  it('allows loopback HTTP URLs for MCP without allow_http (localhost exemption)', async () => {
    const user = userEvent.setup()
    render(<IntegrationForm />, { wrapper })

    await user.type(screen.getByRole('textbox', { name: /name/i }), 'Test MCP')
    await user.type(screen.getByRole('textbox', { name: /api url/i }), 'http://localhost:8765/mcp')
    await user.click(screen.getByRole('button', { name: 'Next' }))

    expect(screen.getByText(/credential is used to discover/i)).toBeInTheDocument()
  })

  it('navigates to integrations list when Cancel is clicked', async () => {
    const user = userEvent.setup()
    render(<IntegrationForm />, { wrapper })

    await user.click(screen.getByRole('button', { name: 'Cancel' }))

    expect(vi.mocked(tanstackRouter.navigate)).toHaveBeenCalledWith(
      expect.objectContaining({ to: '/configuration/integrations' })
    )
  })

  it('navigates back to step 1 when Back is clicked on step 2', async () => {
    const user = userEvent.setup()
    render(<IntegrationForm />, { wrapper })

    await user.type(screen.getByRole('textbox', { name: /name/i }), 'Test MCP')
    await user.type(screen.getByRole('textbox', { name: /api url/i }), 'http://localhost:8765/mcp')
    await user.click(screen.getByRole('button', { name: 'Next' }))

    expect(screen.getByText(/credential is used to discover/i)).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Back' }))

    expect(screen.getByRole('textbox', { name: /name/i })).toBeInTheDocument()
  })

  it('shows Save button on the final step', async () => {
    const user = userEvent.setup()
    render(<IntegrationForm />, { wrapper })

    await user.type(screen.getByRole('textbox', { name: /name/i }), 'Test MCP')
    await user.type(screen.getByRole('textbox', { name: /api url/i }), 'http://localhost:8765/mcp')
    await user.click(screen.getByRole('button', { name: 'Next' }))
    await user.click(screen.getByTestId('select-credential'))
    await user.click(screen.getByRole('button', { name: 'Next' }))

    expect(screen.getByRole('button', { name: 'Save' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Next' })).not.toBeInTheDocument()
  })

  it('calls createIntegration on Save with form data', async () => {
    const mockMutateAsync = vi.fn().mockResolvedValue({ id: 'new-id', name: 'Test' })
    vi.mocked(integrationsClient.useMutation).mockReturnValue({
      mutate: vi.fn(),
      mutateAsync: mockMutateAsync,
      isPending: false,
      isError: false,
    } as never)

    const user = userEvent.setup()
    render(<IntegrationForm />, { wrapper })

    await user.type(screen.getByRole('textbox', { name: /name/i }), 'Test MCP')
    await user.type(screen.getByRole('textbox', { name: /api url/i }), 'http://localhost:8765/mcp')
    await user.click(screen.getByRole('button', { name: 'Next' }))
    await user.click(screen.getByTestId('select-credential'))
    await user.click(screen.getByRole('button', { name: 'Next' }))
    await user.click(screen.getByRole('button', { name: 'Save' }))

    await waitFor(() => {
      expect(mockMutateAsync).toHaveBeenCalled()
    })
  })

  describe('Step 2 credential requirement', () => {
    it('enables Next button on step 2 for MCP when no credential is selected', async () => {
      const user = userEvent.setup()
      render(<IntegrationForm />, { wrapper })

      await advanceToStep2(user)()

      expect(screen.getByRole('button', { name: 'Next' })).not.toHaveAttribute('aria-disabled', 'true')
    })

    it('enables Next button on step 2 after selecting a credential', async () => {
      const user = userEvent.setup()
      render(<IntegrationForm />, { wrapper })

      await advanceToStep2(user)()
      await user.click(screen.getByTestId('select-credential'))

      expect(screen.getByRole('button', { name: 'Next' })).not.toHaveAttribute('aria-disabled', 'true')
    })

    it('can navigate backwards from step 2 to step 1 without credential', async () => {
      const user = userEvent.setup()
      render(<IntegrationForm />, { wrapper })

      await advanceToStep2(user)()
      await user.click(screen.getByRole('button', { name: 'Back' }))

      expect(screen.getByRole('textbox', { name: /name/i })).toBeInTheDocument()
    })

    it('can navigate backwards from step 3 to step 2', async () => {
      const user = userEvent.setup()
      render(<IntegrationForm />, { wrapper })

      await advanceToStep2(user)()
      await user.click(screen.getByRole('button', { name: 'Next' }))
      await user.click(screen.getByRole('button', { name: 'Back' }))

      expect(screen.getByText(/credential is used to discover/i)).toBeInTheDocument()
    })
  })

  describe('Ansible Automation Platform wizard flow', () => {
    async function selectAnsibleAutomationPlatform(user: ReturnType<typeof userEvent.setup>) {
      await user.click(screen.getByText('MCP Server'))
      await user.click(screen.getByText('Ansible Automation Platform'))
    }

    async function advanceAapToStep2(user: ReturnType<typeof userEvent.setup>) {
      await selectAnsibleAutomationPlatform(user)
      await user.type(screen.getByRole('textbox', { name: /name/i }), 'My Ansible Automation Platform')
      await user.type(screen.getByRole('textbox', { name: /api url/i }), 'https://aap.example.com')
      await user.click(screen.getByRole('button', { name: 'Next' }))
    }

    it('shows Ansible Automation Platform as a selectable type option', async () => {
      const user = userEvent.setup()
      render(<IntegrationForm />, { wrapper })

      await user.click(screen.getByText('MCP Server'))

      expect(screen.getByText('Ansible Automation Platform')).toBeInTheDocument()
    })

    it('shows API URL field after selecting Ansible Automation Platform', async () => {
      const user = userEvent.setup()
      render(<IntegrationForm />, { wrapper })

      await selectAnsibleAutomationPlatform(user)

      expect(screen.getByRole('textbox', { name: /api url/i })).toBeInTheDocument()
    })

    it('resets fields when switching from MCP to Ansible Automation Platform', async () => {
      const user = userEvent.setup()
      render(<IntegrationForm />, { wrapper })

      await user.type(screen.getByRole('textbox', { name: /api url/i }), 'http://localhost:8765/mcp')
      await selectAnsibleAutomationPlatform(user)

      expect(screen.getByRole('textbox', { name: /api url/i })).toHaveValue('')
    })

    it('advances to step 2 with valid Ansible Automation Platform fields', async () => {
      const user = userEvent.setup()
      render(<IntegrationForm />, { wrapper })

      await advanceAapToStep2(user)

      expect(screen.getByText(/verify that the Ansible Automation Platform is reachable/i)).toBeInTheDocument()
    })

    it('shows Save button on step 2 (no step 3)', async () => {
      const user = userEvent.setup()
      render(<IntegrationForm />, { wrapper })

      await advanceAapToStep2(user)
      await user.click(screen.getByTestId('select-credential'))

      expect(screen.getByRole('button', { name: 'Save' })).toBeInTheDocument()
      expect(screen.queryByRole('button', { name: 'Next' })).not.toBeInTheDocument()
    })

    it('calls createIntegration with Ansible Automation Platform configuration on Save', async () => {
      const { createAsyncMutate } = mockMutations()

      const user = userEvent.setup()
      render(<IntegrationForm />, { wrapper })

      await advanceAapToStep2(user)
      await user.click(screen.getByTestId('select-credential'))
      await user.click(screen.getByRole('button', { name: 'Save' }))

      await waitFor(() => {
        expect(createAsyncMutate).toHaveBeenCalledWith(
          expect.objectContaining({
            body: expect.objectContaining({
              integration_type: IntegrationTypeEnum.ANSIBLE_AUTOMATION_PLATFORM,
              configuration: expect.objectContaining({
                integration_type: 'ansible_automation_platform',
                base_url: 'https://aap.example.com',
              }) as Record<string, unknown>,
              discovered_tools: null,
            }) as Record<string, unknown>,
          })
        )
      })
    })

    it('disables Save button on step 2 when no credential is selected', async () => {
      const user = userEvent.setup()
      render(<IntegrationForm />, { wrapper })

      await advanceAapToStep2(user)

      expect(screen.getByRole('button', { name: 'Save' })).toHaveAttribute('aria-disabled', 'true')
    })

    it('shows validation error alert when saving with cleared fields', async () => {
      const user = userEvent.setup()
      render(<IntegrationForm />, { wrapper })

      await advanceAapToStep2(user)
      await user.click(screen.getByTestId('select-credential'))

      await user.click(screen.getByRole('button', { name: 'Back' }))
      const nameInput = screen.getByRole('textbox', { name: /name/i })
      const aapUrlInput = screen.getByRole('textbox', { name: /api url/i })
      await user.clear(nameInput)
      await user.clear(aapUrlInput)

      await user.click(screen.getByRole('button', { name: /Connection credential/i }))
      await user.click(screen.getByRole('button', { name: 'Save' }))

      await waitFor(() => {
        expect(screen.getByText('Unable to save integration')).toBeInTheDocument()
      })
    })
  })

  describe('Test connection (discover)', () => {
    it('calls discover endpoint when Test connection is clicked with a credential', async () => {
      const { discoverMutate } = mockMutations()
      const user = userEvent.setup()
      render(<IntegrationForm />, { wrapper })

      await advanceToStep2(user)()
      await user.click(screen.getByTestId('select-credential'))
      await user.click(screen.getByRole('button', { name: 'Test connection' }))

      expect(discoverMutate).toHaveBeenCalledOnce()
      const [reqArg] = discoverMutate.mock.calls[0] as [Record<string, unknown>]
      expect(reqArg.body).toMatchObject({
        integration_type: 'mcp_server',
        credential_id: 'cred-123',
      })
    })

    it('shows success alert when discover returns tools', async () => {
      const discoverMutate = vi.fn()
      discoverMutate.mockImplementation((_body: unknown, callbacks: MutationCallbacks) => {
        callbacks.onSuccess?.({
          success: true,
          discovered_tools: [
            { name: 'tool1', description: 'Tool 1' },
            { name: 'tool2', description: 'Tool 2' },
          ],
        })
      })
      mockMutations(discoverMutate)

      const user = userEvent.setup()
      render(<IntegrationForm />, { wrapper })

      await advanceToStep2(user)()
      await user.click(screen.getByTestId('select-credential'))
      await user.click(screen.getByRole('button', { name: 'Test connection' }))

      await waitFor(() => {
        expect(screen.getByText('Connection tested')).toBeInTheDocument()
        expect(screen.getByText('Successfully connected. Discovered 2 tools.')).toBeInTheDocument()
      })
    })

    it('shows failure alert when discover returns success: false', async () => {
      const discoverMutate = vi.fn()
      discoverMutate.mockImplementation((_body: unknown, callbacks: MutationCallbacks) => {
        callbacks.onSuccess?.({
          success: false,
          error: 'Connection refused: unable to reach MCP server',
        })
      })
      mockMutations(discoverMutate)

      const user = userEvent.setup()
      render(<IntegrationForm />, { wrapper })

      await advanceToStep2(user)()
      await user.click(screen.getByTestId('select-credential'))
      await user.click(screen.getByRole('button', { name: 'Test connection' }))

      await waitFor(() => {
        expect(screen.getByText('Connection failed')).toBeInTheDocument()
        expect(screen.getByText('Connection refused: unable to reach MCP server')).toBeInTheDocument()
      })
    })

    it('shows error alert when discover request fails', async () => {
      const discoverMutate = vi.fn()
      discoverMutate.mockImplementation((_body: unknown, callbacks: MutationCallbacks) => {
        callbacks.onError?.(new Error('Network error'))
      })
      mockMutations(discoverMutate)

      const user = userEvent.setup()
      render(<IntegrationForm />, { wrapper })

      await advanceToStep2(user)()
      await user.click(screen.getByTestId('select-credential'))
      await user.click(screen.getByRole('button', { name: 'Test connection' }))

      await waitFor(() => {
        expect(screen.getByText('Connection test failed')).toBeInTheDocument()
      })
    })

    it('discovered tools appear on step 3 after successful test', async () => {
      const discoverMutate = vi.fn()
      discoverMutate.mockImplementation((_body: unknown, callbacks: MutationCallbacks) => {
        callbacks.onSuccess?.({
          success: true,
          discovered_tools: [
            { name: 'get_repo', description: 'Get repository details' },
            { name: 'create_pr', description: 'Create a pull request' },
          ],
        })
      })
      mockMutations(discoverMutate)

      const user = userEvent.setup()
      render(<IntegrationForm />, { wrapper })

      await advanceToStep2(user)()
      await user.click(screen.getByTestId('select-credential'))
      await user.click(screen.getByRole('button', { name: 'Test connection' }))

      await waitFor(() => {
        expect(screen.getByText('Connection tested')).toBeInTheDocument()
      })

      await user.click(screen.getByRole('button', { name: 'Next' }))

      expect(screen.getByText('get_repo')).toBeInTheDocument()
      expect(screen.getByText('create_pr')).toBeInTheDocument()
    })

    it('enables test connection for MCP when no credential is selected', async () => {
      const user = userEvent.setup()
      render(<IntegrationForm />, { wrapper })

      await advanceToStep2(user)()

      expect(screen.getByRole('button', { name: 'Test connection' })).not.toHaveAttribute('aria-disabled', 'true')
    })

    it('calls discover for MCP without credential', async () => {
      const { discoverMutate } = mockMutations()
      const user = userEvent.setup()
      render(<IntegrationForm />, { wrapper })

      await advanceToStep2(user)()
      await user.click(screen.getByRole('button', { name: 'Test connection' }))

      expect(discoverMutate).toHaveBeenCalledOnce()
      const [reqArg] = discoverMutate.mock.calls[0] as [Record<string, unknown>]
      expect(reqArg.body).toMatchObject({
        integration_type: 'mcp_server',
      })
    })
  })

  it('has no accessibility violations', async () => {
    const { container } = render(<IntegrationForm />, { wrapper })
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  describe('LLM Provider wizard flow', () => {
    async function selectLLMProvider(user: ReturnType<typeof userEvent.setup>) {
      const typeToggle = screen.getByText('MCP Server')
      await user.click(typeToggle)
      await user.click(screen.getByRole('option', { name: 'LLM Provider' }))
    }

    async function advanceLLMToStep2(user: ReturnType<typeof userEvent.setup>) {
      await selectLLMProvider(user)
      await user.type(screen.getByRole('textbox', { name: 'Name' }), 'Test LLM')
      await user.type(screen.getByRole('textbox', { name: /api url/i }), 'https://api.example.com')
      await user.click(screen.getByRole('button', { name: 'Next' }))
    }

    it('shows LLM Provider option in integration type selector', async () => {
      const user = userEvent.setup()
      render(<IntegrationForm />, { wrapper })

      await user.click(screen.getByText('MCP Server'))

      expect(screen.getByRole('option', { name: 'LLM Provider' })).toBeInTheDocument()
    })

    it('shows provider hint and name fields after selecting LLM Provider', async () => {
      const user = userEvent.setup()
      render(<IntegrationForm />, { wrapper })

      await selectLLMProvider(user)

      expect(screen.getByText('Red Hat AI')).toBeInTheDocument()
      expect(screen.getByRole('textbox', { name: 'Name' })).toBeInTheDocument()
    })

    it('step 3 shows Enable models for LLM provider', async () => {
      const discoverMutate = vi.fn()
      discoverMutate.mockImplementation((_body: unknown, callbacks: MutationCallbacks) => {
        callbacks.onSuccess?.({
          success: true,
          discovered_models: [{ id: 'm1', name: 'model-1', description: 'A model' }],
        })
      })
      mockMutations(discoverMutate)

      const user = userEvent.setup()
      render(<IntegrationForm />, { wrapper })

      await advanceLLMToStep2(user)
      await user.click(screen.getByTestId('select-credential'))
      await user.click(screen.getByRole('button', { name: 'Test connection' }))

      await waitFor(() => {
        expect(screen.getByText('Connection tested')).toBeInTheDocument()
      })

      await user.click(screen.getByRole('button', { name: 'Next' }))

      expect(screen.getByText('model-1')).toBeInTheDocument()
    })

    it('test connection returns discovered_models for LLM providers', async () => {
      const discoverMutate = vi.fn()
      discoverMutate.mockImplementation((_body: unknown, callbacks: MutationCallbacks) => {
        callbacks.onSuccess?.({
          success: true,
          discovered_models: [
            { id: 'm1', name: 'model-1', description: 'First' },
            { id: 'm2', name: 'model-2', description: 'Second' },
          ],
        })
      })
      mockMutations(discoverMutate)

      const user = userEvent.setup()
      render(<IntegrationForm />, { wrapper })

      await advanceLLMToStep2(user)
      await user.click(screen.getByTestId('select-credential'))
      await user.click(screen.getByRole('button', { name: 'Test connection' }))

      await waitFor(() => {
        expect(screen.getByText('Successfully connected. Discovered 2 models.')).toBeInTheDocument()
      })
    })

    it('changing credential clears test result', async () => {
      const discoverMutate = vi.fn()
      discoverMutate.mockImplementation((_body: unknown, callbacks: MutationCallbacks) => {
        callbacks.onSuccess?.({
          success: true,
          discovered_models: [{ id: 'm1', name: 'model-1', description: 'A model' }],
        })
      })
      mockMutations(discoverMutate)

      const user = userEvent.setup()
      render(<IntegrationForm />, { wrapper })

      await advanceLLMToStep2(user)
      await user.click(screen.getByTestId('select-credential'))
      await user.click(screen.getByRole('button', { name: 'Test connection' }))

      await waitFor(() => {
        expect(screen.getByText('Connection tested')).toBeInTheDocument()
      })

      await user.click(screen.getByTestId('clear-credential'))

      expect(screen.getByRole('button', { name: 'Next' })).toHaveAttribute('aria-disabled', 'true')
    })

    it('calls createIntegration with discovered models on Save for LLM', async () => {
      const discoverMutate = vi.fn()
      discoverMutate.mockImplementation((_body: unknown, callbacks: MutationCallbacks) => {
        callbacks.onSuccess?.({
          success: true,
          discovered_models: [
            { id: 'm1', name: 'model-1', description: 'First' },
            { id: 'm2', name: 'model-2', description: 'Second' },
          ],
        })
      })
      const { createAsyncMutate } = mockMutations(discoverMutate)

      const user = userEvent.setup()
      render(<IntegrationForm />, { wrapper })

      await advanceLLMToStep2(user)
      await user.click(screen.getByTestId('select-credential'))
      await user.click(screen.getByRole('button', { name: 'Test connection' }))

      await waitFor(() => {
        expect(screen.getByText('Connection tested')).toBeInTheDocument()
      })

      await user.click(screen.getByRole('button', { name: 'Next' }))
      await user.click(screen.getByRole('button', { name: 'Save' }))

      await waitFor(() => {
        expect(createAsyncMutate).toHaveBeenCalledWith(
          expect.objectContaining({
            body: expect.objectContaining({
              integration_type: IntegrationTypeEnum.LLM_PROVIDER,
              discovered_models: expect.arrayContaining([
                expect.objectContaining({ model_id: 'm1', name: 'model-1', enabled: true }),
              ]) as unknown[],
            }) as Record<string, unknown>,
          })
        )
      })
    })

    it('MCP server flow still works unchanged (regression)', async () => {
      const user = userEvent.setup()
      render(<IntegrationForm />, { wrapper })

      await user.type(screen.getByRole('textbox', { name: /name/i }), 'Test MCP')
      await user.type(screen.getByRole('textbox', { name: /api url/i }), 'http://localhost:8765/mcp')
      await user.click(screen.getByRole('button', { name: 'Next' }))

      expect(screen.getByText(/credential is used to discover/i)).toBeInTheDocument()
    })

    it('LLM Provider disables Next on step 2 without credential', async () => {
      const user = userEvent.setup()
      render(<IntegrationForm />, { wrapper })

      await user.click(screen.getByText('MCP Server'))
      await user.click(screen.getByRole('option', { name: 'LLM Provider' }))
      await user.type(screen.getByRole('textbox', { name: 'Name' }), 'Test LLM')
      await user.type(screen.getByRole('textbox', { name: /api url/i }), 'https://api.example.com')
      await user.click(screen.getByRole('button', { name: 'Next' }))

      expect(screen.getByText(/credential is used to verify/i)).toBeInTheDocument()
      expect(screen.getByRole('button', { name: 'Next' })).toHaveAttribute('aria-disabled', 'true')
    })

    it('LLM Provider disables test connection without credential', async () => {
      const user = userEvent.setup()
      render(<IntegrationForm />, { wrapper })

      await user.click(screen.getByText('MCP Server'))
      await user.click(screen.getByRole('option', { name: 'LLM Provider' }))
      await user.type(screen.getByRole('textbox', { name: 'Name' }), 'Test LLM')
      await user.type(screen.getByRole('textbox', { name: /api url/i }), 'https://api.example.com')
      await user.click(screen.getByRole('button', { name: 'Next' }))

      expect(screen.getByRole('button', { name: 'Test connection' })).toHaveAttribute('aria-disabled', 'true')
    })
  })

  describe('Validation error alert on save', () => {
    it('shows validation error alert with name error when saving MCP form with cleared name', async () => {
      const user = userEvent.setup()
      render(<IntegrationForm />, { wrapper })

      await user.type(screen.getByRole('textbox', { name: /name/i }), 'Test MCP')
      await user.type(screen.getByRole('textbox', { name: /api url/i }), 'http://localhost:8765/mcp')
      await user.click(screen.getByRole('button', { name: 'Next' }))

      await user.click(screen.getByTestId('select-credential'))
      await user.click(screen.getByRole('button', { name: 'Next' }))

      await user.click(screen.getByRole('button', { name: 'Back' }))
      await user.click(screen.getByRole('button', { name: 'Back' }))

      const nameInput = screen.getByRole('textbox', { name: /name/i })
      await user.clear(nameInput)
      const urlInput = screen.getByRole('textbox', { name: /api url/i })
      await user.clear(urlInput)

      await user.click(screen.getByRole('button', { name: /Enable tools/i }))
      await user.click(screen.getByRole('button', { name: 'Save' }))

      await waitFor(() => {
        expect(screen.getByText('Unable to save integration')).toBeInTheDocument()
      })
    })
  })

  describe('Test connection disabled during testing', () => {
    it('disables test connection and step navigation when testing is in progress', async () => {
      vi.mocked(integrationsClient.useMutation).mockImplementation((_method: string, path: string) => {
        if (path === '/integrations/discover') {
          return { mutate: vi.fn(), mutateAsync: vi.fn(), isPending: true, isError: false } as never
        }
        return {
          mutate: vi.fn(),
          mutateAsync: vi.fn().mockResolvedValue({ id: 'new-id' }),
          isPending: false,
          isError: false,
        } as never
      })

      const user = userEvent.setup()
      render(<IntegrationForm />, { wrapper })

      await user.type(screen.getByRole('textbox', { name: /name/i }), 'Test MCP')
      await user.type(screen.getByRole('textbox', { name: /api url/i }), 'http://localhost:8765/mcp')
      await user.click(screen.getByRole('button', { name: 'Next' }))

      await user.click(screen.getByTestId('select-credential'))

      expect(screen.getByRole('button', { name: /test connection/i })).toHaveAttribute('aria-disabled', 'true')
    })
  })
})
