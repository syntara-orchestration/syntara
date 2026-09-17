import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi, beforeEach } from 'vitest'

import { createAgenticActivity } from '../../../stores/useWorkflowStore'
import type { CreateAgenticActivityOptions } from '../../../stores/workflowFactories'

import { AIAgentNodeDetails } from './AIAgentNodeDetails'

// Mock the workflow store
const mockUpdateActivity = vi.fn()
vi.mock('../../../stores/useWorkflowStore', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../../stores/useWorkflowStore')>()),
  useWorkflowStore: vi.fn((selector?: (store: { updateActivity: typeof mockUpdateActivity }) => unknown) => {
    const store = {
      updateActivity: mockUpdateActivity,
    }
    return selector ? selector(store) : store
  }),
  useWorkflowStoreActions: vi.fn(() => ({
    updateActivity: mockUpdateActivity,
  })),
  createAgenticActivity: vi.fn((options: CreateAgenticActivityOptions) => ({
    type: 'agentic',
    id: options.id,
    name: options.name,
    parameters: {
      ...(options.toolSelections && options.toolSelections.length > 0 && { tool_selections: options.toolSelections }),
      ...(options.toolSelections?.length === 0 && { tool_selection_strategy: 'NONE' }),
      ...(options.prompt && { prompt: options.prompt }),
      ...(options.llmModelId && { llm_model_id: options.llmModelId }),
      ...(options.fileIds && options.fileIds.length > 0 && { file_ids: options.fileIds }),
    },
  })),
}))

// Mock the alerts hook
const mockShowError = vi.fn()
vi.mock('../../../providers/alerts', () => ({
  useAlerts: vi.fn(() => ({
    showSuccess: vi.fn(),
    showError: mockShowError,
  })),
}))

// Mock AIAgentNodeForm
vi.mock('../node-forms/AIAgentNodeForm', () => ({
  AIAgentNodeForm: ({
    onSubmit,
    onCancel,
    initialData,
    existingFileIds,
    submitButtonText,
  }: {
    onSubmit: (data: Record<string, unknown>) => void
    onCancel: () => void
    initialData?: {
      name?: string
      llm_model_id?: string
      prompt?: string
      tool_selections?: string[]
      integration_connections?: { integration_id: string; credential_id: string }[]
      credential_id?: string
      responseSchema?: string
    }
    existingFileIds?: string[]
    submitButtonText?: string
  }) => (
    <div data-testid="ai-agent-form">
      <div data-testid="initial-name">{initialData?.name ?? ''}</div>
      <div data-testid="initial-model">{initialData?.llm_model_id ?? ''}</div>
      <div data-testid="initial-prompt">{initialData?.prompt ?? ''}</div>
      <div data-testid="initial-tool-selections">{(initialData?.tool_selections ?? []).join(', ')}</div>
      <div data-testid="initial-credential-id">{initialData?.credential_id ?? ''}</div>
      <div data-testid="initial-response-schema">{initialData?.responseSchema ?? ''}</div>
      <div data-testid="initial-integration-connections">
        {String((initialData?.integration_connections ?? []).length)}
      </div>
      <button
        onClick={() =>
          onSubmit({
            name: 'Updated Agent',
            llm_model_id: 'test-model-uuid',
            prompt: 'Updated prompt',
            tool_selections: ['calculator', 'web_search'],
            integration_connections: [],
            fileIds: existingFileIds ?? [],
            settings: { timeout: 30 },
          })
        }
        data-testid="submit-button"
      >
        {submitButtonText ?? 'Add step'}
      </button>
      <button onClick={onCancel} data-testid="cancel-button">
        Cancel
      </button>
    </div>
  ),
}))

describe('AIAgentNodeDetails Component', () => {
  const mockOnClose = vi.fn()

  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('calls updateActivity on successful form submission', async () => {
    const user = userEvent.setup()
    const taskData = {
      type: 'agentic' as const,
      id: 'agent-1',
      name: 'Original Agent',
      parameters: {
        llm_model_id: 'original-model-uuid',
        prompt: 'Original prompt',
      },
    }

    render(<AIAgentNodeDetails taskData={taskData} nodeId="agent-1" onClose={mockOnClose} />)

    await user.click(screen.getByTestId('submit-button'))

    expect(mockUpdateActivity).toHaveBeenCalledWith(
      'agent-1',
      expect.objectContaining({
        type: 'agentic',
        id: 'agent-1',
        name: 'Updated Agent',
        // eslint-disable-next-line @typescript-eslint/no-unsafe-assignment
        parameters: expect.objectContaining({
          llm_model_id: 'test-model-uuid',
          prompt: 'Updated prompt',
          tool_selections: ['calculator', 'web_search'],
        }),
      })
    )
  })

  it('calls onClose after successful update', async () => {
    const user = userEvent.setup()
    const taskData = {
      type: 'agentic' as const,
      id: 'agent-1',
      name: 'Test Agent',
      parameters: {},
    }

    render(<AIAgentNodeDetails taskData={taskData} nodeId="agent-1" onClose={mockOnClose} />)

    await user.click(screen.getByTestId('submit-button'))

    expect(mockOnClose).toHaveBeenCalledTimes(1)
  })

  it('handles empty tool_selections', () => {
    const taskData = {
      type: 'agentic' as const,
      id: 'agent-1',
      name: 'Test Agent',
      parameters: {
        tool_selections: [],
      },
    }

    render(<AIAgentNodeDetails taskData={taskData} nodeId="agent-1" onClose={mockOnClose} />)

    expect(screen.getByTestId('initial-tool-selections')).toHaveTextContent('')
  })

  it('shows error when updateActivity throws', async () => {
    const user = userEvent.setup()
    mockUpdateActivity.mockImplementationOnce(() => {
      throw new Error('The update failed')
    })
    const taskData = {
      type: 'agentic' as const,
      id: 'agent-1',
      name: 'Test Agent',
      parameters: {},
    }

    render(<AIAgentNodeDetails taskData={taskData} nodeId="agent-1" onClose={mockOnClose} />)

    await user.click(screen.getByTestId('submit-button'))

    expect(mockShowError).toHaveBeenCalledWith({ title: 'Update failed', description: 'The update failed' })
  })

  it('preserves task inputs when updating', async () => {
    const user = userEvent.setup()
    const taskData = {
      type: 'agentic' as const,
      id: 'agent-1',
      name: 'Test Agent',
      parameters: {},
    }

    render(<AIAgentNodeDetails taskData={taskData} nodeId="agent-1" onClose={mockOnClose} />)

    await user.click(screen.getByTestId('submit-button'))

    expect(createAgenticActivity).toHaveBeenCalledWith(
      expect.objectContaining({
        id: 'agent-1',
        name: 'Updated Agent',
      })
    )
    expect(mockUpdateActivity).toHaveBeenCalled()
  })

  it('passes settings to createAgenticActivity on submit', async () => {
    const user = userEvent.setup()
    const taskData = {
      type: 'agentic' as const,
      id: 'agent-1',
      name: 'Test Agent',
      parameters: {},
    }

    render(<AIAgentNodeDetails taskData={taskData} nodeId="agent-1" onClose={mockOnClose} />)

    await user.click(screen.getByTestId('submit-button'))

    expect(createAgenticActivity).toHaveBeenCalledWith(
      expect.objectContaining({
        settings: { timeout: 30 },
      })
    )
  })

  it('reads tool_selections from config', () => {
    const taskData = {
      type: 'agentic' as const,
      id: 'agent-1',
      name: 'Tool Agent',
      parameters: {},
      config: {
        tool_selections: ['list_resources', 'get_resource'],
      },
    }

    render(<AIAgentNodeDetails taskData={taskData} nodeId="agent-1" onClose={mockOnClose} />)

    expect(screen.getByTestId('initial-tool-selections')).toHaveTextContent('list_resources, get_resource')
  })
})

describe('AIAgentNodeDetails config/parameters fallback logic', () => {
  const mockOnClose = vi.fn()

  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('reads all fields from config when config is present', async () => {
    const user = userEvent.setup()
    const taskData = {
      type: 'agentic' as const,
      id: 'agent-1',
      name: 'Agent',
      parameters: {},
      config: {
        tool_selections: ['tool-a', 'tool-b'],
        integration_connections: [{ integration_id: 'int-1', credential_id: 'cred-x' }],
        credential_id: 'llm-cred',
        response_schema: { type: 'object' },
        file_ids: ['file-1'],
      },
    }

    render(<AIAgentNodeDetails taskData={taskData} nodeId="agent-1" onClose={mockOnClose} />)

    expect(screen.getByTestId('initial-tool-selections')).toHaveTextContent('tool-a, tool-b')
    expect(screen.getByTestId('initial-credential-id')).toHaveTextContent('llm-cred')
    expect(screen.getByTestId('initial-response-schema')).toHaveTextContent('"type"')
    expect(screen.getByTestId('initial-integration-connections')).toHaveTextContent('1')

    await user.click(screen.getByTestId('submit-button'))
    expect(createAgenticActivity).toHaveBeenCalledWith(expect.objectContaining({ fileIds: ['file-1'] }))
  })

  it('falls back to parameters when config is absent', async () => {
    const user = userEvent.setup()
    const taskData = {
      type: 'agentic' as const,
      id: 'agent-1',
      name: 'Agent',
      parameters: {
        tool_selections: ['tool-p'],
        integration_connections: [{ integration_id: 'int-2', credential_id: 'cred-y' }],
        credential_id: 'param-cred',
        response_schema: { type: 'string' },
        file_ids: ['file-p'],
      },
    }

    render(<AIAgentNodeDetails taskData={taskData} nodeId="agent-1" onClose={mockOnClose} />)

    expect(screen.getByTestId('initial-tool-selections')).toHaveTextContent('tool-p')
    expect(screen.getByTestId('initial-credential-id')).toHaveTextContent('param-cred')
    expect(screen.getByTestId('initial-response-schema')).toHaveTextContent('"type"')
    expect(screen.getByTestId('initial-integration-connections')).toHaveTextContent('1')

    await user.click(screen.getByTestId('submit-button'))
    expect(createAgenticActivity).toHaveBeenCalledWith(expect.objectContaining({ fileIds: ['file-p'] }))
  })

  it('config values win when both config and parameters are present', () => {
    const taskData = {
      type: 'agentic' as const,
      id: 'agent-1',
      name: 'Agent',
      parameters: {
        tool_selections: ['param-tool'],
        credential_id: 'param-cred',
      },
      config: {
        tool_selections: ['config-tool'],
        credential_id: 'config-cred',
      },
    }

    render(<AIAgentNodeDetails taskData={taskData} nodeId="agent-1" onClose={mockOnClose} />)

    expect(screen.getByTestId('initial-tool-selections')).toHaveTextContent('config-tool')
    expect(screen.getByTestId('initial-credential-id')).toHaveTextContent('config-cred')
  })

  it('uses responseSchema (camelCase) alias when response_schema is absent', () => {
    const taskData = {
      type: 'agentic' as const,
      id: 'agent-1',
      name: 'Agent',
      parameters: {},
      config: {
        responseSchema: { type: 'array' },
      },
    }

    render(<AIAgentNodeDetails taskData={taskData} nodeId="agent-1" onClose={mockOnClose} />)

    expect(screen.getByTestId('initial-response-schema')).toHaveTextContent('"type"')
    expect(screen.getByTestId('initial-response-schema')).toHaveTextContent('"array"')
  })

  it('uses fileIds (camelCase) alias when file_ids is absent', async () => {
    const user = userEvent.setup()
    const taskData = {
      type: 'agentic' as const,
      id: 'agent-1',
      name: 'Agent',
      parameters: {},
      config: {
        fileIds: ['camel-file-1'],
      },
    }

    render(<AIAgentNodeDetails taskData={taskData} nodeId="agent-1" onClose={mockOnClose} />)

    await user.click(screen.getByTestId('submit-button'))
    expect(createAgenticActivity).toHaveBeenCalledWith(expect.objectContaining({ fileIds: ['camel-file-1'] }))
  })

  it('uses tools alias when tool_selections is absent', () => {
    const taskData = {
      type: 'agentic' as const,
      id: 'agent-1',
      name: 'Agent',
      parameters: {},
      config: {
        tools: ['legacy-tool-1', 'legacy-tool-2'],
      },
    }

    render(<AIAgentNodeDetails taskData={taskData} nodeId="agent-1" onClose={mockOnClose} />)

    expect(screen.getByTestId('initial-tool-selections')).toHaveTextContent('legacy-tool-1, legacy-tool-2')
  })

  it('defaults all fields gracefully when neither config nor parameters is present', async () => {
    const user = userEvent.setup()
    const taskData = {
      type: 'agentic' as const,
      id: 'agent-1',
      name: 'Bare Agent',
      parameters: {},
    }

    render(<AIAgentNodeDetails taskData={taskData} nodeId="agent-1" onClose={mockOnClose} />)

    expect(screen.getByTestId('initial-tool-selections')).toHaveTextContent('')
    expect(screen.getByTestId('initial-credential-id')).toHaveTextContent('')
    expect(screen.getByTestId('initial-response-schema')).toHaveTextContent('')
    expect(screen.getByTestId('initial-integration-connections')).toHaveTextContent('0')

    await user.click(screen.getByTestId('submit-button'))
    // No existing file IDs — only submitted files matter (mock submits none)
    expect(createAgenticActivity).toHaveBeenCalledWith(expect.objectContaining({ fileIds: undefined }))
  })
})
