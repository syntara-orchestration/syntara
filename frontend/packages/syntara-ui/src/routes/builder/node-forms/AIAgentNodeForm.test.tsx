import { fireEvent, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { credentialsClient, integrationsClient } from '../../../client'
import { useFileStorageStatus } from '../../../hooks/useFileStorageStatus'
import { useFileUploadWithProgress } from '../../../hooks/useFileUploadWithProgress'
import { useAllProjects, useSelectableProjects } from '../../access/useAllProjects'
import { useIntegrationPermissions } from '../../configuration/integrations/useIntegrationPermissions'

import { AIAgentNodeForm } from './AIAgentNodeForm'
import { renderWithHeader } from './test-utils/renderWithHeader'
import { useAllEnabledMcpIntegrations } from './useAllEnabledMcpIntegrations'
import { useAllTools } from './useAllTools'

// Mock clients used by CredentialSelector, LLMModelSelector
vi.mock('../../../client', () => ({
  credentialsClient: {
    useQuery: vi.fn(),
    useMutation: vi.fn(),
  },
  integrationsClient: {
    useQuery: vi.fn(() => ({ data: { resources: [] }, isPending: false, isError: false, refetch: vi.fn() })),
    useMutation: vi.fn(),
  },
  integrationsFetchClient: {
    GET: vi.fn(() => Promise.resolve({ data: { resources: [] } })),
  },
  authMiddleware: { onRequest: vi.fn(({ request }: { request: unknown }) => request) },
  interfaceTagMiddleware: { onRequest: vi.fn() },
}))

vi.mock('./useAllTools', () => ({
  useAllTools: vi.fn(() => ({ tools: [], isLoading: false, isError: false, refetch: vi.fn() })),
}))

vi.mock('./useAllEnabledMcpIntegrations', () => ({
  useAllEnabledMcpIntegrations: vi.fn(() => ({
    integrations: [],
    isLoading: false,
    isError: false,
    refetch: vi.fn(),
  })),
}))

vi.mock('../../access/useAllProjects', () => ({
  useAllProjects: vi.fn(),
  useSelectableProjects: vi.fn(),
}))

// Mock file upload hook
const mockUploadFiles = vi.fn()
vi.mock('../../../hooks/useFileUploadWithProgress', () => ({
  useFileUploadWithProgress: vi.fn(),
}))

vi.mock('../../../hooks/useFileStorageStatus', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../../hooks/useFileStorageStatus')>()),
  useFileStorageStatus: vi
    .fn()
    .mockReturnValue({ isConfigured: true, isLoading: false, isError: false, status: 'ok' as const }),
}))

// Mock FileUpload component to expose file selection handler
vi.mock('../components/file-upload', () => ({
  FileUpload: ({
    onFilesSelected,
    onFileRemove,
    files = [],
    disabled,
    disabledTooltip,
  }: {
    onFilesSelected: (files: File[]) => void
    onFileRemove: (id: string) => void
    files?: Array<{ id: string; file: File; status: string }>
    disabled?: boolean
    disabledTooltip?: string
  }) => (
    <div data-testid="file-upload" data-disabled={disabled} data-disabled-tooltip={disabledTooltip}>
      <button
        data-testid="upload-files"
        onClick={() => {
          const file = new File(['test'], 'test.txt', { type: 'text/plain' })
          onFilesSelected([file])
        }}
      >
        Upload
      </button>
      {(files || []).map((f) => (
        <div key={f.id} data-testid={`file-${f.id}`}>
          <span>{f.file.name}</span>
          <span data-testid={`file-status-${f.id}`}>{f.status}</span>
          <button data-testid={`remove-${f.id}`} onClick={() => onFileRemove(f.id)}>
            Remove
          </button>
        </div>
      ))}
    </div>
  ),
}))

vi.mock('../../configuration/integrations/useIntegrationPermissions', () => ({
  useIntegrationPermissions: vi.fn(() => ({
    canCreate: true,
    canUpdate: false,
    canDelete: false,
    isLoading: false,
    tooltips: { create: '', update: '', enable: '', validate: '', delete: '' },
  })),
}))

vi.mock('../../../utils/deleteFile', () => ({
  deleteFileById: vi.fn(() => Promise.resolve()),
}))

// Mock generateUUID
vi.mock('../../../utils/generateUUID', () => ({
  generateUUID: vi.fn(() => 'mock-uuid-123'),
}))

// Mock ExpandableCodeEditor to use a simple input for testing
vi.mock('../components/ExpandableCodeEditor', () => ({
  ExpandableCodeEditor: ({
    code,
    onCodeChange,
    ariaLabel,
  }: {
    code: string
    onCodeChange: (code: string) => void
    ariaLabel?: string
  }) => (
    <input
      data-testid="response-schema-editor"
      id="agent-response-schema"
      value={code}
      onChange={(e) => onCodeChange(e.target.value)}
      aria-label={ariaLabel}
    />
  ),
}))

describe('AIAgentNodeForm', () => {
  const mockOnSubmit = vi.fn()

  beforeEach(() => {
    vi.clearAllMocks()
    mockOnSubmit.mockReset()
    vi.mocked(credentialsClient.useQuery).mockReturnValue({
      data: { resources: [] },
      isPending: false,
      error: null,
      refetch: vi.fn(),
    } as never)
    vi.mocked(credentialsClient.useMutation).mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
    } as never)
    vi.mocked(useAllProjects).mockReturnValue({ projects: [], isLoading: false, error: null, refetch: vi.fn() })
    vi.mocked(useSelectableProjects).mockReturnValue({ projects: [], isLoading: false, error: null, refetch: vi.fn() })
    vi.mocked(useFileStorageStatus).mockReturnValue({
      isConfigured: true,
      isLoading: false,
      isError: false,
      status: 'ok' as const,
    })
    vi.mocked(useFileUploadWithProgress).mockReturnValue({
      uploadFiles: mockUploadFiles,
      progress: [],
      error: null,
      uploading: false,
      cancelUpload: vi.fn(),
      reset: vi.fn(),
    })
    mockUploadFiles.mockResolvedValue({
      files: [{ file_id: 'server-file-123', filename: 'test.txt', size_bytes: 4 }],
    })
  })

  it('renders form with all fields', () => {
    renderWithHeader(<AIAgentNodeForm onSubmit={mockOnSubmit} />)

    expect(screen.getByLabelText('Name')).toBeInTheDocument()
    expect(screen.getByRole('textbox', { name: 'Prompt' })).toBeInTheDocument()
    expect(screen.getByLabelText('Tools')).toBeInTheDocument()
  })

  it('submits form even with empty prompt (permissive schema)', async () => {
    const user = userEvent.setup()
    renderWithHeader(<AIAgentNodeForm onSubmit={mockOnSubmit} initialData={{ name: '', llm_model_id: 'model-1' }} />)

    await user.type(screen.getByPlaceholderText(/Enter agent name/i), 'Test Agent')
    fireEvent.submit(screen.getByTestId('ai-agent-node-form'))

    await waitFor(() => {
      expect(mockOnSubmit).toHaveBeenCalledWith(
        expect.objectContaining({
          name: 'Test Agent',
        })
      )
    })
  })

  it('populates form with initial data', () => {
    renderWithHeader(
      <AIAgentNodeForm
        onSubmit={mockOnSubmit}
        initialData={{
          name: 'Existing Agent',
          llm_model_id: '550e8400-e29b-41d4-a716-446655440000',
          prompt: 'Analyze the data',
          tool_selections: [],
        }}
      />
    )

    expect(screen.getByDisplayValue('Existing Agent')).toBeInTheDocument()
    expect(screen.getByDisplayValue('Analyze the data')).toBeInTheDocument()
    expect(screen.getByLabelText('Tools')).toBeInTheDocument()
  })

  it('hides credential section when no model is selected', () => {
    renderWithHeader(<AIAgentNodeForm onSubmit={mockOnSubmit} projectId="project-789" />)

    expect(screen.queryByLabelText('LLM provider credential')).not.toBeInTheDocument()
    expect(screen.queryByText(/LLM credential not configured/i)).not.toBeInTheDocument()
  })

  it('renders interactive tools multi-select', () => {
    renderWithHeader(<AIAgentNodeForm onSubmit={mockOnSubmit} />)

    const toolsSelect = screen.getByLabelText('Tools')
    expect(toolsSelect).toBeInTheDocument()
    expect(toolsSelect).not.toBeDisabled()
  })

  it('renders file upload component', () => {
    renderWithHeader(<AIAgentNodeForm onSubmit={mockOnSubmit} />)

    expect(screen.getByTestId('file-upload')).toBeInTheDocument()
  })

  it('handles file upload success', async () => {
    const user = userEvent.setup()
    renderWithHeader(<AIAgentNodeForm onSubmit={mockOnSubmit} projectId="project-789" />)

    await user.click(screen.getByTestId('upload-files'))

    await waitFor(() => {
      expect(mockUploadFiles).toHaveBeenCalled()
    })
  })

  it('forwards projectId to uploadFiles when uploading files', async () => {
    const user = userEvent.setup()
    renderWithHeader(<AIAgentNodeForm onSubmit={mockOnSubmit} projectId="project-789" />)

    await user.click(screen.getByTestId('upload-files'))

    await waitFor(() => {
      expect(mockUploadFiles).toHaveBeenCalledWith(expect.any(Array), 'project-789')
    })
  })

  it('disables file upload with helper text when no projectId', () => {
    renderWithHeader(<AIAgentNodeForm onSubmit={mockOnSubmit} />)

    const fileUpload = screen.getByTestId('file-upload')
    expect(fileUpload).toHaveAttribute('data-disabled', 'true')
    expect(fileUpload).toHaveAttribute(
      'data-disabled-tooltip',
      'Select a project in the workflow builder header to upload context files.'
    )
    expect(
      screen.getByText('Select a project in the workflow builder header to upload context files.')
    ).toBeInTheDocument()
  })

  it('handles file upload error', async () => {
    const user = userEvent.setup()
    mockUploadFiles.mockRejectedValueOnce(new Error('Upload failed'))

    renderWithHeader(<AIAgentNodeForm onSubmit={mockOnSubmit} projectId="project-789" />)

    await user.click(screen.getByTestId('upload-files'))

    await waitFor(() => {
      expect(mockUploadFiles).toHaveBeenCalled()
    })
  })

  it('handles file removal', async () => {
    const user = userEvent.setup()
    renderWithHeader(<AIAgentNodeForm onSubmit={mockOnSubmit} projectId="project-789" />)

    // Upload a file first
    await user.click(screen.getByTestId('upload-files'))

    await waitFor(() => {
      expect(mockUploadFiles).toHaveBeenCalled()
    })

    // Wait for file to appear
    await waitFor(() => {
      expect(screen.getByText('test.txt')).toBeInTheDocument()
    })

    // Click remove button (server-backed files delete via API before leaving the UI)
    const removeButton = screen.getByTestId('remove-server-file-123')
    await user.click(removeButton)

    await waitFor(() => {
      expect(screen.queryByText('test.txt')).not.toBeInTheDocument()
    })
  })

  it('after submit, removing a persisted upload detaches without DELETE', async () => {
    const user = userEvent.setup()
    const { deleteFileById } = await import('../../../utils/deleteFile')
    vi.mocked(deleteFileById).mockClear()

    renderWithHeader(
      <AIAgentNodeForm
        onSubmit={mockOnSubmit}
        projectId="project-789"
        initialData={{ name: 'Agent', llm_model_id: 'model-1', prompt: 'Do stuff' }}
      />
    )

    await user.click(screen.getByTestId('upload-files'))
    await waitFor(() => {
      expect(screen.getByText('test.txt')).toBeInTheDocument()
    })

    fireEvent.submit(screen.getByTestId('ai-agent-node-form'))
    await waitFor(() => {
      expect(mockOnSubmit).toHaveBeenCalledWith(
        expect.objectContaining({
          fileIds: ['server-file-123'],
        })
      )
    })

    vi.mocked(deleteFileById).mockClear()
    await user.click(screen.getByTestId('remove-server-file-123'))

    await waitFor(() => {
      expect(screen.queryByText('test.txt')).not.toBeInTheDocument()
    })
    expect(deleteFileById).not.toHaveBeenCalled()
  })

  it('when onSubmit returns false, remove still DELETEs the session upload', async () => {
    const user = userEvent.setup()
    const { deleteFileById } = await import('../../../utils/deleteFile')
    vi.mocked(deleteFileById).mockClear()
    mockOnSubmit.mockReturnValue(false)

    renderWithHeader(
      <AIAgentNodeForm
        onSubmit={mockOnSubmit}
        projectId="project-789"
        initialData={{ name: 'Agent', llm_model_id: 'model-1', prompt: 'Do stuff' }}
      />
    )

    await user.click(screen.getByTestId('upload-files'))
    await waitFor(() => {
      expect(screen.getByText('test.txt')).toBeInTheDocument()
    })

    fireEvent.submit(screen.getByTestId('ai-agent-node-form'))
    await waitFor(() => {
      expect(mockOnSubmit).toHaveBeenCalled()
    })

    vi.mocked(deleteFileById).mockClear()
    await user.click(screen.getByTestId('remove-server-file-123'))

    await waitFor(() => {
      expect(deleteFileById).toHaveBeenCalledWith('server-file-123')
    })
  })

  it('when onSubmit throws, remove still DELETEs the session upload', async () => {
    const user = userEvent.setup()
    const { deleteFileById } = await import('../../../utils/deleteFile')
    vi.mocked(deleteFileById).mockClear()
    mockOnSubmit.mockImplementation(() => {
      throw new Error('Add step failed')
    })

    renderWithHeader(
      <AIAgentNodeForm
        onSubmit={mockOnSubmit}
        projectId="project-789"
        initialData={{ name: 'Agent', llm_model_id: 'model-1', prompt: 'Do stuff' }}
      />
    )

    await user.click(screen.getByTestId('upload-files'))
    await waitFor(() => {
      expect(screen.getByText('test.txt')).toBeInTheDocument()
    })

    fireEvent.submit(screen.getByTestId('ai-agent-node-form'))
    await waitFor(() => {
      expect(mockOnSubmit).toHaveBeenCalled()
    })

    vi.mocked(deleteFileById).mockClear()
    await user.click(screen.getByTestId('remove-server-file-123'))

    await waitFor(() => {
      expect(deleteFileById).toHaveBeenCalledWith('server-file-123')
    })
  })

  it('when onSubmit resolves false, remove still DELETEs the session upload', async () => {
    const user = userEvent.setup()
    const { deleteFileById } = await import('../../../utils/deleteFile')
    vi.mocked(deleteFileById).mockClear()
    mockOnSubmit.mockResolvedValue(false)

    renderWithHeader(
      <AIAgentNodeForm
        onSubmit={mockOnSubmit}
        projectId="project-789"
        initialData={{ name: 'Agent', llm_model_id: 'model-1', prompt: 'Do stuff' }}
      />
    )

    await user.click(screen.getByTestId('upload-files'))
    await waitFor(() => {
      expect(screen.getByText('test.txt')).toBeInTheDocument()
    })

    fireEvent.submit(screen.getByTestId('ai-agent-node-form'))
    await waitFor(() => {
      expect(mockOnSubmit).toHaveBeenCalled()
    })

    vi.mocked(deleteFileById).mockClear()
    await user.click(screen.getByTestId('remove-server-file-123'))

    await waitFor(() => {
      expect(deleteFileById).toHaveBeenCalledWith('server-file-123')
    })
  })

  describe('Response Schema', () => {
    it('renders response schema editor', () => {
      renderWithHeader(<AIAgentNodeForm onSubmit={mockOnSubmit} />)

      const schemaEditor = screen.getByLabelText('Response schema editor')
      expect(schemaEditor).toBeInTheDocument()
      expect(schemaEditor).toHaveAttribute('aria-label', 'Response schema editor')
      expect(screen.getByText(/Optional JSON Schema to enforce structured output format/i)).toBeInTheDocument()
    })

    it('submits form with valid JSON object in response schema', async () => {
      const user = userEvent.setup()
      renderWithHeader(<AIAgentNodeForm onSubmit={mockOnSubmit} initialData={{ name: '', llm_model_id: 'model-1' }} />)

      // Fill fields
      await user.type(screen.getByPlaceholderText(/Enter agent name/i), 'Test Agent')
      await user.type(screen.getByPlaceholderText(/Natural language instructions/i), 'Test prompt')

      // Add valid JSON using paste
      const schemaEditor = screen.getByLabelText('Response schema editor')
      await user.click(schemaEditor)
      await user.paste('{"type": "object"}')

      // Submit form
      fireEvent.submit(screen.getByTestId('ai-agent-node-form'))

      await waitFor(() => {
        expect(mockOnSubmit).toHaveBeenCalled()
      })
    })

    it('rejects non-object response schema', async () => {
      const user = userEvent.setup()
      renderWithHeader(<AIAgentNodeForm onSubmit={mockOnSubmit} initialData={{ name: '', llm_model_id: 'model-1' }} />)

      // Fill fields
      await user.type(screen.getByPlaceholderText(/Enter agent name/i), 'Test Agent')
      await user.type(screen.getByPlaceholderText(/Natural language instructions/i), 'Test prompt')

      // Add array instead of object using paste
      const schemaEditor = screen.getByLabelText('Response schema editor')
      await user.click(schemaEditor)
      await user.paste('["item1", "item2"]')

      // Submit form
      fireEvent.submit(screen.getByTestId('ai-agent-node-form'))

      await waitFor(() => {
        expect(screen.getByText('Response schema must be a JSON object')).toBeInTheDocument()
      })
      expect(mockOnSubmit).not.toHaveBeenCalled()
    })

    it('pre-fills response schema in edit mode', () => {
      const existingSchema = { type: 'object', properties: { name: { type: 'string' } } }
      const initialData = {
        name: 'Existing Agent',
        prompt: 'Existing prompt',
        llm_model_id: '550e8400-e29b-41d4-a716-446655440000',
        tool_selections: [] as string[],
        integration_connections: [] as { integration_id: string; credential_id: string }[],
        responseSchema: JSON.stringify(existingSchema, null, 2),
      }

      renderWithHeader(<AIAgentNodeForm onSubmit={mockOnSubmit} initialData={initialData} />)

      const schemaEditor = screen.getByLabelText('Response schema editor')
      // Check that the value contains the schema (formatting may vary)
      const value = (schemaEditor as HTMLInputElement).value
      expect(value).toContain('"type"')
      expect(value).toContain('"object"')
      expect(value).toContain('"properties"')
      expect(value).toContain('"name"')
    })
  })

  describe('Tools integration', () => {
    const mockTools = [
      {
        id: 'tool-1',
        name: 'list_repos',
        namespaced_name: 'github::list_repos',
        integration_id: 'int-1',
        enabled: true,
        parameters: [],
      },
      {
        id: 'tool-2',
        name: 'create_issue',
        namespaced_name: 'github::create_issue',
        integration_id: 'int-1',
        enabled: true,
        parameters: [],
      },
      {
        id: 'tool-3',
        name: 'send_message',
        namespaced_name: 'slack::send_message',
        integration_id: 'int-2',
        enabled: true,
        parameters: [],
      },
      {
        id: 'tool-4',
        name: 'deprecated_tool',
        namespaced_name: 'github::deprecated_tool',
        integration_id: 'int-1',
        enabled: false,
        parameters: [],
      },
      {
        id: 'tool-5',
        name: 'orphan_tool',
        namespaced_name: 'unknown::orphan_tool',
        integration_id: 'int-999',
        enabled: true,
        parameters: [],
      },
    ]

    const mockIntegrations = [
      { id: 'int-1', name: 'GitHub Copilot', integration_type: 'mcp_server', enabled: true },
      { id: 'int-2', name: 'Slack Bot', integration_type: 'mcp_server', enabled: true },
    ]

    function setupToolMocks({
      tools = mockTools,
      integrations = mockIntegrations,
      isToolsError = false,
      isIntegrationsError = false,
    }: {
      tools?: typeof mockTools
      integrations?: typeof mockIntegrations
      isToolsError?: boolean
      isIntegrationsError?: boolean
    } = {}) {
      const refetchTools = vi.fn().mockResolvedValue({})
      const refetchIntegrations = vi.fn().mockResolvedValue({})

      vi.mocked(useAllTools).mockReturnValue({
        tools,
        isLoading: false,
        isError: isToolsError,
        refetch: refetchTools,
      } as never)

      vi.mocked(useAllEnabledMcpIntegrations).mockReturnValue({
        integrations,
        isLoading: false,
        isError: isIntegrationsError,
        refetch: refetchIntegrations,
      } as never)

      return { refetchTools, refetchIntegrations }
    }

    it('renders tools grouped by integration when data is available', async () => {
      const user = userEvent.setup()
      setupToolMocks()

      renderWithHeader(<AIAgentNodeForm onSubmit={mockOnSubmit} />)

      await user.click(screen.getByRole('button', { name: 'Tools' }))

      expect(screen.getByText('GitHub Copilot')).toBeInTheDocument()
      expect(screen.getByText('Slack Bot')).toBeInTheDocument()
      expect(screen.getByText('list_repos')).toBeInTheDocument()
      expect(screen.getByText('create_issue')).toBeInTheDocument()
      expect(screen.getByText('send_message')).toBeInTheDocument()
    })

    it('filters out disabled tools', async () => {
      const user = userEvent.setup()
      setupToolMocks()

      renderWithHeader(<AIAgentNodeForm onSubmit={mockOnSubmit} />)

      await user.click(screen.getByRole('button', { name: 'Tools' }))

      expect(screen.queryByText('deprecated_tool')).not.toBeInTheDocument()
    })

    it('filters out tools whose integration is not in the integrations list', async () => {
      const user = userEvent.setup()
      setupToolMocks()

      renderWithHeader(<AIAgentNodeForm onSubmit={mockOnSubmit} />)

      await user.click(screen.getByRole('button', { name: 'Tools' }))

      expect(screen.queryByText('orphan_tool')).not.toBeInTheDocument()
    })

    it('shows "All tools selected" when initialData has ALL strategy', () => {
      setupToolMocks()

      renderWithHeader(
        <AIAgentNodeForm
          onSubmit={mockOnSubmit}
          initialData={{ tool_selection_strategy: 'ALL', tool_selections: [] }}
        />
      )

      expect(screen.getByDisplayValue('All tools selected')).toBeInTheDocument()
    })

    it('shows selected count when initialData has SELECTED strategy', () => {
      setupToolMocks()

      renderWithHeader(
        <AIAgentNodeForm
          onSubmit={mockOnSubmit}
          initialData={{ tool_selection_strategy: 'SELECTED', tool_selections: ['tool-1'] }}
        />
      )

      expect(screen.getByDisplayValue('1 of 3 tools selected')).toBeInTheDocument()
    })

    it('shows error with retry button when tools query fails', () => {
      setupToolMocks({ isToolsError: true })

      renderWithHeader(<AIAgentNodeForm onSubmit={mockOnSubmit} />)

      expect(screen.getByText(/Failed to load tools or integrations/)).toBeInTheDocument()
      expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument()
    })

    it('shows error with retry button when integrations query fails', () => {
      setupToolMocks({ isIntegrationsError: true })

      renderWithHeader(<AIAgentNodeForm onSubmit={mockOnSubmit} />)

      expect(screen.getByText(/Failed to load tools or integrations/)).toBeInTheDocument()
    })

    it('calls refetch on both queries when retry is clicked', async () => {
      const user = userEvent.setup()
      const { refetchTools, refetchIntegrations } = setupToolMocks({ isToolsError: true })

      renderWithHeader(<AIAgentNodeForm onSubmit={mockOnSubmit} />)

      await user.click(screen.getByRole('button', { name: 'Retry' }))

      expect(refetchTools).toHaveBeenCalled()
      expect(refetchIntegrations).toHaveBeenCalled()
    })

    it('shows helper text with link when no MCP integrations and user has create permission', () => {
      renderWithHeader(<AIAgentNodeForm onSubmit={mockOnSubmit} />)

      expect(screen.getByText('configure an MCP server integration')).toBeInTheDocument()
      const link = screen.getByRole('link', { name: 'configure an MCP server integration' })
      expect(link).toHaveAttribute('href', '/configuration/integrations/configure')
    })

    it('shows helper text without link when no MCP integrations and user lacks create permission', () => {
      vi.mocked(useIntegrationPermissions).mockReturnValue({
        canCreate: false,
        canUpdate: false,
        canDelete: false,
        isLoading: false,
        tooltips: { create: '', update: '', enable: '', validate: '', delete: '' },
      })

      renderWithHeader(<AIAgentNodeForm onSubmit={mockOnSubmit} />)

      const helperTexts = screen.getAllByText(/before tools can be selected/)
      expect(helperTexts.length).toBeGreaterThan(0)
      expect(screen.queryByRole('link', { name: 'configure an MCP server integration' })).not.toBeInTheDocument()
    })

    it('does not show MCP helper text when integrations are available', () => {
      setupToolMocks()

      renderWithHeader(<AIAgentNodeForm onSubmit={mockOnSubmit} />)

      expect(screen.queryByText('configure an MCP server integration')).not.toBeInTheDocument()
      expect(screen.queryByText(/before tools can be selected/)).not.toBeInTheDocument()
    })

    it('shows loading state while integrations query is still pending', () => {
      vi.mocked(useAllTools).mockReturnValue({
        tools: mockTools,
        isLoading: false,
        isError: false,
        refetch: vi.fn().mockResolvedValue({}),
      } as never)

      vi.mocked(useAllEnabledMcpIntegrations).mockReturnValue({
        integrations: [],
        isLoading: true,
        isError: false,
        refetch: vi.fn().mockResolvedValue({}),
      } as never)

      renderWithHeader(<AIAgentNodeForm onSubmit={mockOnSubmit} />)

      expect(screen.getByPlaceholderText('Loading tools...')).toBeInTheDocument()
    })

    describe('Stale tool cleanup', () => {
      it('removes stale tool selections and shows warning', () => {
        setupToolMocks()

        renderWithHeader(
          <AIAgentNodeForm
            onSubmit={mockOnSubmit}
            initialData={{
              tool_selection_strategy: 'SELECTED',
              tool_selections: ['tool-1', 'stale-tool-id'],
            }}
          />
        )

        expect(screen.getByText(/1 previously selected tool is no longer available/)).toBeInTheDocument()
        expect(screen.getByDisplayValue('1 of 3 tools selected')).toBeInTheDocument()
      })

      it('resets to NONE when all selected tools are stale', () => {
        setupToolMocks()

        renderWithHeader(
          <AIAgentNodeForm
            onSubmit={mockOnSubmit}
            initialData={{
              tool_selection_strategy: 'SELECTED',
              tool_selections: ['stale-1', 'stale-2'],
            }}
          />
        )

        expect(screen.getByText(/2 previously selected tools are no longer available/)).toBeInTheDocument()
        expect(screen.getByDisplayValue('No tools selected')).toBeInTheDocument()
      })

      it('does not show warning when all selected tools are valid', () => {
        setupToolMocks()

        renderWithHeader(
          <AIAgentNodeForm
            onSubmit={mockOnSubmit}
            initialData={{
              tool_selection_strategy: 'SELECTED',
              tool_selections: ['tool-1', 'tool-3'],
            }}
          />
        )

        expect(screen.queryByText(/no longer available/)).not.toBeInTheDocument()
        expect(screen.getByDisplayValue('2 of 3 tools selected')).toBeInTheDocument()
      })

      it('does not clean tools when strategy is ALL', () => {
        setupToolMocks()

        renderWithHeader(
          <AIAgentNodeForm
            onSubmit={mockOnSubmit}
            initialData={{
              tool_selection_strategy: 'ALL',
              tool_selections: [],
            }}
          />
        )

        expect(screen.queryByText(/no longer available/)).not.toBeInTheDocument()
        expect(screen.getByDisplayValue('All tools selected')).toBeInTheDocument()
      })

      it('does not clean tools while integrations are still loading', () => {
        vi.mocked(useAllTools).mockReturnValue({
          tools: [],
          isLoading: true,
          isError: false,
          refetch: vi.fn().mockResolvedValue({}),
        } as never)

        vi.mocked(useAllEnabledMcpIntegrations).mockReturnValue({
          integrations: [],
          isLoading: true,
          isError: false,
          refetch: vi.fn().mockResolvedValue({}),
        } as never)

        renderWithHeader(
          <AIAgentNodeForm
            onSubmit={mockOnSubmit}
            initialData={{
              tool_selection_strategy: 'SELECTED',
              tool_selections: ['stale-1'],
            }}
          />
        )

        expect(screen.queryByText(/no longer available/)).not.toBeInTheDocument()
      })
    })

    it('submits tool_selection_strategy and tool_selections with form data', async () => {
      setupToolMocks()

      renderWithHeader(
        <AIAgentNodeForm
          onSubmit={mockOnSubmit}
          initialData={{
            name: 'Agent',
            llm_model_id: 'model-1',
            tool_selection_strategy: 'ALL',
            tool_selections: [],
          }}
        />
      )

      fireEvent.submit(screen.getByTestId('ai-agent-node-form'))

      await waitFor(() => {
        expect(mockOnSubmit).toHaveBeenCalledWith(
          expect.objectContaining({
            tool_selection_strategy: 'ALL',
            tool_selections: [],
          })
        )
      })
    })
  })

  describe('file storage status', () => {
    it('shows permanent tooltip when S3 is unconfigured', () => {
      vi.mocked(useFileStorageStatus).mockReturnValue({
        isConfigured: false,
        isLoading: false,
        isError: false,
        status: 'unconfigured' as const,
      })
      renderWithHeader(<AIAgentNodeForm onSubmit={mockOnSubmit} projectId="test-project" />)

      const fileUpload = screen.getByTestId('file-upload')
      expect(fileUpload).toHaveAttribute('data-disabled', 'true')
      expect(fileUpload).toHaveAttribute(
        'data-disabled-tooltip',
        'File uploads are disabled. Contact your platform administrator to configure S3 storage.'
      )
    })

    it('shows transient tooltip when S3 is degraded', () => {
      vi.mocked(useFileStorageStatus).mockReturnValue({
        isConfigured: false,
        isLoading: false,
        isError: false,
        status: 'degraded' as const,
      })
      renderWithHeader(<AIAgentNodeForm onSubmit={mockOnSubmit} projectId="test-project" />)

      const fileUpload = screen.getByTestId('file-upload')
      expect(fileUpload).toHaveAttribute('data-disabled', 'true')
      expect(fileUpload).toHaveAttribute(
        'data-disabled-tooltip',
        'File uploads are temporarily unavailable. S3 storage is experiencing issues.'
      )
    })
  })

  describe('retry policy visibility', () => {
    it('hides retry policy for AI agent nodes', async () => {
      const user = userEvent.setup()
      renderWithHeader(<AIAgentNodeForm onSubmit={mockOnSubmit} />)

      await user.click(screen.getByRole('tab', { name: 'Settings' }))

      expect(screen.queryByRole('switch', { name: 'Override retry policy' })).not.toBeInTheDocument()
    })
  })

  describe('project scoping', () => {
    it('passes projectId to the MCP integrations hook when provided', () => {
      renderWithHeader(<AIAgentNodeForm onSubmit={mockOnSubmit} projectId="proj-abc" />)
      expect(useAllEnabledMcpIntegrations).toHaveBeenCalledWith('proj-abc')
    })

    it('passes projectId to the LLM integrations query when projectId is provided', () => {
      renderWithHeader(<AIAgentNodeForm onSubmit={mockOnSubmit} projectId="proj-abc" />)
      expect(integrationsClient.useQuery).toHaveBeenCalledWith('get', '/integrations', {
        params: {
          query: { integration_type: 'llm_provider', enabled: true, project_id: 'proj-abc' },
        },
      })
    })

    it('does not include project_id in integration queries when projectId is omitted', () => {
      renderWithHeader(<AIAgentNodeForm onSubmit={mockOnSubmit} />)
      expect(useAllEnabledMcpIntegrations).toHaveBeenCalledWith(undefined)
      expect(integrationsClient.useQuery).toHaveBeenCalledWith('get', '/integrations', {
        params: {
          query: { integration_type: 'llm_provider', enabled: true },
        },
      })
    })
  })

  describe('Accessibility', () => {
    it('has no accessibility violations (excluding known PatternFly Tabs issue)', async () => {
      const { container } = renderWithHeader(<AIAgentNodeForm onSubmit={mockOnSubmit} />)
      // Note: PatternFly Tabs have a known aria-controls issue in testing (tabs work correctly in real browsers)
      // Excluding this known issue from our accessibility tests
      const results = await axe(container, {
        rules: {
          'aria-valid-attr-value': { enabled: false },
        },
      })
      expect(results).toHaveNoViolations()
    })

    it('has no accessibility violations with response schema filled (excluding known PatternFly Tabs issue)', async () => {
      const user = userEvent.setup()
      const { container } = renderWithHeader(<AIAgentNodeForm onSubmit={mockOnSubmit} />)

      // Fill response schema using paste
      const validSchema = JSON.stringify({ type: 'object' }, null, 2)
      const schemaEditor = screen.getByLabelText('Response schema editor')
      await user.click(schemaEditor)
      await user.paste(validSchema)

      const results = await axe(container, {
        rules: {
          'aria-valid-attr-value': { enabled: false },
        },
      })
      expect(results).toHaveNoViolations()
    })

    it('has no accessibility violations after submitting with response schema (excluding known PatternFly Tabs issue)', async () => {
      const user = userEvent.setup()
      const { container } = renderWithHeader(
        <AIAgentNodeForm onSubmit={mockOnSubmit} initialData={{ name: '', llm_model_id: 'model-1' }} />
      )

      // Fill fields
      await user.type(screen.getByPlaceholderText(/Enter agent name/i), 'Test Agent')
      await user.type(screen.getByPlaceholderText(/Natural language instructions/i), 'Test prompt')

      // Add valid JSON using paste
      const schemaEditor = screen.getByLabelText('Response schema editor')
      await user.click(schemaEditor)
      await user.paste('{"type": "object"}')

      // Submit form (permissive schema allows this)
      fireEvent.submit(screen.getByTestId('ai-agent-node-form'))

      await waitFor(() => {
        expect(mockOnSubmit).toHaveBeenCalled()
      })

      const results = await axe(container, {
        rules: {
          'aria-valid-attr-value': { enabled: false },
        },
      })
      expect(results).toHaveNoViolations()
    })
  })
})
