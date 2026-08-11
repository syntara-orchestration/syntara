import type { Activity, TaskActivity } from '@syntara/contracts'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { useAlerts } from '../../../providers/alerts'
import * as workflowStore from '../../../stores/useWorkflowStore'
import type { WorkflowStore } from '../../../stores/useWorkflowStore'

import { TaskNodeDetails } from './TaskNodeDetails'

const mockUpdateActivity = vi.fn()
const mockCreateAAPJobTemplateActivity = vi.fn()

vi.spyOn(workflowStore, 'useWorkflowStore')
vi.spyOn(workflowStore, 'useWorkflowStoreActions')
vi.spyOn(workflowStore, 'createAAPJobTemplateActivity')

// Mock the alerts hook
const mockShowError = vi.fn()
vi.mock('../../../providers/alerts', () => ({
  useAlerts: vi.fn(),
}))

// Mock ActionNodeForm
vi.mock('../node-forms/ActionNodeForm', () => ({
  ActionNodeForm: ({
    onSubmit,
    onCancel,
    submitButtonText,
  }: {
    onSubmit: (data: Record<string, unknown>) => void
    onCancel: () => void
    submitButtonText?: string
  }) => (
    <div data-testid="action-node-form">
      <button onClick={() => onSubmit({ name: 'Updated Task', executor: 'script' })} data-testid="submit-button">
        {submitButtonText ?? 'Add step'}
      </button>
      <button
        onClick={() =>
          onSubmit({
            name: 'Updated API Task',
            executor: 'http_request',
            method: 'POST',
            url: 'https://api.test.com',
            headers: [{ id: 'h1', key: 'Content-Type', value: 'application/json' }],
            body: '{"data": "test"}',
          })
        }
        data-testid="submit-api-button"
      >
        Submit API
      </button>
      <button
        onClick={() =>
          onSubmit({
            name: 'API with Invalid Body',
            executor: 'http_request',
            method: 'POST',
            url: 'https://api.test.com',
            body: 'plain text body',
          })
        }
        data-testid="submit-api-plain-body-button"
      >
        Submit API Plain Body
      </button>
      <button
        onClick={() =>
          onSubmit({
            name: 'API with Invalid Headers',
            executor: 'http_request',
            method: 'POST',
            url: 'https://api.test.com',
            headers: [{ id: 'h1', key: '', value: 'ignored' }],
          })
        }
        data-testid="submit-api-invalid-headers-button"
      >
        Submit API Invalid Headers
      </button>
      <button
        onClick={() =>
          onSubmit({
            name: 'API with Credential',
            executor: 'http_request',
            method: 'GET',
            url: 'https://api.test.com',
            credential_id: 'cred-123',
          })
        }
        data-testid="submit-api-credential-button"
      >
        Submit API with Credential
      </button>
      <button
        onClick={() =>
          onSubmit({
            name: 'API with Follow Redirects',
            executor: 'http_request',
            method: 'GET',
            url: 'https://api.test.com',
            follow_redirects: true,
          })
        }
        data-testid="submit-api-follow-redirects-button"
      >
        Submit API with Follow Redirects
      </button>
      <button onClick={onCancel} data-testid="cancel-button">
        Cancel
      </button>
    </div>
  ),
}))

// Mock AAPJobTemplateForm
vi.mock('../node-forms/AAPJobTemplateForm', () => ({
  AAPJobTemplateForm: ({
    onSubmit,
    onCancel,
    submitButtonText,
  }: {
    onSubmit: (data: Record<string, unknown>) => void
    onCancel: () => void
    submitButtonText?: string
    onHeaderContentChange: (content: ReactNode | null) => void
  }) => (
    <div data-testid="aap-node-form">
      <button
        onClick={() =>
          onSubmit({
            name: 'Updated AAP Task',
            job_template_id: 456,
            inventory_name: '789',
            extra_vars: '{"key": "value"}',
            limit: 'servers',
            tags: 'install',
            skip_tags: 'debug',
            verbosity: '3',
          })
        }
        data-testid="aap-submit-button"
      >
        {submitButtonText ?? 'Add step'}
      </button>
      <button onClick={onCancel} data-testid="aap-cancel-button">
        Cancel
      </button>
    </div>
  ),
}))

// Mock AAPWorkflowTemplateForm
vi.mock('../node-forms/AAPWorkflowTemplateForm', () => ({
  AAPWorkflowTemplateForm: ({
    onSubmit,
    onCancel,
    submitButtonText,
  }: {
    onSubmit: (data: Record<string, unknown>) => void
    onCancel: () => void
    submitButtonText?: string
    onHeaderContentChange: (content: ReactNode | null) => void
  }) => (
    <div data-testid="aap-workflow-template-form">
      <button
        onClick={() =>
          onSubmit({
            name: 'Updated Workflow Task',
            workflow_job_template_id: 789,
            inventory_name: 'Workflow Inventory',
            extra_vars: '{"workflow": "data"}',
          })
        }
        data-testid="workflow-submit-button"
      >
        {submitButtonText ?? 'Add step'}
      </button>
      <button onClick={onCancel} data-testid="workflow-cancel-button">
        Cancel
      </button>
    </div>
  ),
}))

// Mock AIAgentNodeDetails
vi.mock('./AIAgentNodeDetails', () => ({
  AIAgentNodeDetails: ({
    taskData,
    nodeId,
    onClose,
  }: {
    taskData: Record<string, unknown>
    nodeId: string
    onClose: () => void
  }) => (
    <div data-testid="ai-agent-node-details">
      <div data-testid="agent-node-id">{nodeId}</div>
      <div data-testid="agent-task-name">{String(taskData.name)}</div>
      <button onClick={onClose} data-testid="agent-close-button">
        Close
      </button>
    </div>
  ),
}))

describe('TaskNodeDetails Component', () => {
  const mockOnClose = vi.fn()
  const renderTaskNodeDetails = (taskData: TaskActivity, nodeId: string) =>
    render(
      <TaskNodeDetails taskData={taskData} nodeId={nodeId} onClose={mockOnClose} onHeaderContentChange={vi.fn()} />
    )

  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(workflowStore.useWorkflowStore).mockImplementation((selector?: (state: WorkflowStore) => unknown) => {
      const store = {
        updateActivity: mockUpdateActivity,
      }
      return selector ? selector(store as unknown as WorkflowStore) : store
    })
    vi.mocked(workflowStore.useWorkflowStoreActions).mockImplementation(() => ({
      updateActivity: mockUpdateActivity,
      setWorkflow: vi.fn(),
      loadWorkflowWithEdges: vi.fn(),
      updateWorkflow: vi.fn(),
      markClean: vi.fn(),
      markDirty: vi.fn(),
      setEdges: vi.fn(),
      addTrigger: vi.fn(),
      removeTrigger: vi.fn(),
      updateTrigger: vi.fn(),
      addActivity: vi.fn(),
      removeActivity: vi.fn(),
      replaceActivity: vi.fn(),
      duplicateActivity: vi.fn(),
      updateSwitchActivity: vi.fn(),
      moveActivityBefore: vi.fn(),
      moveActivityAfter: vi.fn(),
      reorderActivitiesFromEdges: vi.fn(),
      batchRemoveNodesAndEdges: vi.fn(),
      batchAddActivitiesAndEdges: vi.fn(),
      updateNodePositions: vi.fn(),
      clearNodePositions: vi.fn(),
    }))
    vi.mocked(workflowStore.createAAPJobTemplateActivity).mockImplementation(mockCreateAAPJobTemplateActivity)
    vi.mocked(useAlerts).mockReturnValue({
      showSuccess: vi.fn(),
      showError: mockShowError,
      showAlert: vi.fn(),
      showWarning: vi.fn(),
      showInfo: vi.fn(),
      dismissAlert: vi.fn(),
      clearAllAlerts: vi.fn(),
    })
    // Setup mockCreateAAPJobTemplateActivity to return proper activity structure
    mockCreateAAPJobTemplateActivity.mockImplementation(
      (id: string, name: string, job_template_id: number, config?: Record<string, unknown>) => ({
        type: 'aap_job_template' as const,
        id,
        name,
        parameters: {
          job_template_id,
          ...config,
        },
      })
    )
  })

  it('renders ActionNodeForm for script task', () => {
    const taskData = {
      type: 'script' as const,
      id: 'task-1',
      name: 'Script Task',
      parameters: {
        language: 'python' as const,
        code: 'print("hello")',
      },
    }

    renderTaskNodeDetails(taskData, 'task-1')

    expect(screen.getByTestId('action-node-form')).toBeInTheDocument()
  })

  it('renders ActionNodeForm for API task', () => {
    const taskData = {
      type: 'http_request' as const,
      id: 'task-2',
      name: 'API Task',
      parameters: {
        method: 'GET' as const,
        url: 'https://api.example.com',
      },
    }

    renderTaskNodeDetails(taskData, 'task-2')

    expect(screen.getByTestId('action-node-form')).toBeInTheDocument()
  })

  it('renders AAPNodeForm for aap_job_template task', () => {
    const taskData = {
      type: 'aap_job_template' as const,
      id: 'task-aap',
      name: 'AAP Task',
      parameters: {
        job_template_id: 123,
        inventory_id: 456,
        extra_vars: { foo: 'bar' },
      },
    }

    renderTaskNodeDetails(taskData, 'task-aap')

    expect(screen.getByTestId('aap-node-form')).toBeInTheDocument()
  })

  it('renders AAPNodeForm with minimal config (only job_template_id)', () => {
    const taskData = {
      type: 'aap_job_template' as const,
      id: 'task-aap-minimal',
      name: 'Minimal AAP Task',
      parameters: {
        job_template_id: 789,
      },
    }

    renderTaskNodeDetails(taskData, 'task-aap-minimal')

    expect(screen.getByTestId('aap-node-form')).toBeInTheDocument()
  })

  it('renders AAPNodeForm for expression mode config (job_template_name without job_template_id)', () => {
    const taskData = {
      type: 'aap_job_template' as const,
      id: 'task-aap-expr',
      name: 'Expression AAP Task',
      parameters: {
        job_template_name: '${trigger.template}',
        organization_name: '${trigger.org}',
        credential_id: 'cred-abc',
      },
    }

    renderTaskNodeDetails(taskData, 'task-aap-expr')

    expect(screen.getByTestId('aap-node-form')).toBeInTheDocument()
  })

  it('renders AIAgentNodeDetails for agentic task', () => {
    const taskData = {
      type: 'agentic' as const,
      id: 'task-agent',
      name: 'Task Agent',
      parameters: {
        model: 'claude-3-sonnet',
        prompt: 'Analyze the data',
        tool_selections: ['calculator', 'web_search'],
      },
    }

    renderTaskNodeDetails(taskData, 'task-agent')

    expect(screen.getByTestId('ai-agent-node-details')).toBeInTheDocument()
    expect(screen.getByTestId('agent-node-id')).toHaveTextContent('task-agent')
    expect(screen.getByTestId('agent-task-name')).toHaveTextContent('Task Agent')
  })

  it('returns null for unsupported executor type', () => {
    const taskData = {
      type: 'unsupported' as never,
      id: 'task-3',
      name: 'Unsupported Task',
      parameters: {},
    }

    const { container } = renderTaskNodeDetails(taskData, 'task-3')

    expect(container).toBeEmptyDOMElement()
  })

  it('calls updateActivity on successful form submission', async () => {
    const user = userEvent.setup()
    const taskData = {
      type: 'script' as const,
      id: 'task-1',
      name: 'Original Task',
      parameters: {
        language: 'python' as const,
        code: 'print("original")',
      },
    }

    renderTaskNodeDetails(taskData, 'task-1')

    await user.click(screen.getByTestId('submit-button'))

    expect(mockUpdateActivity).toHaveBeenCalledWith('task-1', expect.objectContaining({ name: 'Updated Task' }))
  })

  it('calls updateActivity on successful AAP form submission', async () => {
    const user = userEvent.setup()
    const taskData = {
      type: 'aap_job_template' as const,
      id: 'task-aap',
      name: 'AAP Task',
      parameters: {
        job_template_id: 123,
        inventory_id: 456,
        job_credentials: [1, 2, 3],
        extra_vars: { env: 'prod' },
        limit: 'webservers',
        tags: 'deploy',
        skip_tags: 'testing',
        verbosity: 2 as const,
      },
    }

    renderTaskNodeDetails(taskData, 'task-aap')

    await user.click(screen.getByTestId('aap-submit-button'))

    // AAP nodes use aap_job_template type directly in v2
    expect(mockUpdateActivity).toHaveBeenCalledWith(
      'task-aap',
      expect.objectContaining({
        name: 'Updated AAP Task',
        // eslint-disable-next-line @typescript-eslint/no-unsafe-assignment
        parameters: expect.objectContaining({
          job_template_id: 456,
        }),
      })
    )
  })

  it('renders form with initial data', () => {
    const taskData = {
      type: 'script' as const,
      id: 'task-1',
      name: 'Task',
      parameters: {
        language: 'python' as const,
        code: 'print("test")',
      },
    }

    renderTaskNodeDetails(taskData, 'task-1')

    expect(screen.getByTestId('action-node-form')).toBeInTheDocument()
  })

  it('returns null for approval node (type approval)', () => {
    const taskData = {
      type: 'approval' as const,
      id: 'task-approval',
      name: 'Approval Task',
      parameters: {
        approver_timeout: 3600,
      },
    } as unknown as TaskActivity

    const { container } = renderTaskNodeDetails(taskData, 'task-approval')

    expect(container).toBeEmptyDOMElement()
  })

  it('handles API form submission with headers and body', async () => {
    const user = userEvent.setup()
    const taskData = {
      type: 'http_request' as const,
      id: 'task-api',
      name: 'API Task',
      parameters: {
        method: 'GET' as const,
        url: 'https://api.example.com',
      },
    }

    renderTaskNodeDetails(taskData, 'task-api')

    await user.click(screen.getByTestId('submit-api-button'))

    expect(mockUpdateActivity).toHaveBeenCalledWith(
      'task-api',
      expect.objectContaining({
        name: 'Updated API Task',
        // eslint-disable-next-line @typescript-eslint/no-unsafe-assignment
        parameters: expect.objectContaining({
          method: 'POST',
          url: 'https://api.test.com',
          headers: { 'Content-Type': 'application/json' },
          body: { data: 'test' },
        }),
      })
    )
  })

  it('loads stored headers into initial data for http_request', () => {
    const taskData = {
      type: 'http_request' as const,
      id: 'task-api-headers',
      name: 'API With Headers',
      parameters: {
        method: 'POST' as const,
        url: 'https://api.example.com',
        headers: { Accept: 'application/json', 'X-Custom': 'value' },
      },
    }

    renderTaskNodeDetails(taskData, 'task-api-headers')

    expect(screen.getByTestId('action-node-form')).toBeInTheDocument()
  })

  it('stores credential_id in snake_case in workflow config (AAP-73929)', async () => {
    const user = userEvent.setup()
    const taskData = {
      type: 'http_request' as const,
      id: 'task-api-cred',
      name: 'API Task',
      parameters: {
        method: 'GET' as const,
        url: 'https://api.example.com',
      },
    }

    renderTaskNodeDetails(taskData, 'task-api-cred')

    await user.click(screen.getByTestId('submit-api-credential-button'))

    expect(mockUpdateActivity).toHaveBeenCalledWith(
      'task-api-cred',
      expect.objectContaining({
        // eslint-disable-next-line @typescript-eslint/no-unsafe-assignment
        parameters: expect.objectContaining({
          credential_id: 'cred-123',
        }),
      })
    )
    // Must NOT use camelCase — backend looks for credential_id
    const callArgs = mockUpdateActivity.mock.calls[0] as [string, { parameters: Record<string, unknown> }]
    expect(callArgs[1].parameters).not.toHaveProperty('credentialId')
  })

  it('handles API form submission with plain text body', async () => {
    const user = userEvent.setup()
    const taskData = {
      type: 'http_request' as const,
      id: 'task-api',
      name: 'API Task',
      parameters: {
        method: 'GET' as const,
        url: 'https://api.example.com',
      },
    }

    renderTaskNodeDetails(taskData, 'task-api')

    await user.click(screen.getByTestId('submit-api-plain-body-button'))

    expect(mockUpdateActivity).toHaveBeenCalledWith(
      'task-api',
      expect.objectContaining({
        // eslint-disable-next-line @typescript-eslint/no-unsafe-assignment
        parameters: expect.objectContaining({
          body: 'plain text body',
        }),
      })
    )
  })

  it('renders API task with inputs/parameters', () => {
    const taskData = {
      type: 'http_request' as const,
      id: 'task-api-params',
      name: 'API Task with Params',
      parameters: {
        method: 'POST' as const,
        url: 'https://api.example.com',
      },
      inputs: {
        userId: '{{user.id}}',
        timestamp: '{{now}}',
      },
    }

    renderTaskNodeDetails(taskData, 'task-api-params')

    expect(screen.getByTestId('action-node-form')).toBeInTheDocument()
  })

  it('renders API task with string body in config', () => {
    const taskData = {
      type: 'http_request' as const,
      id: 'task-api-string-body',
      name: 'API Task with String Body',
      parameters: {
        method: 'POST' as const,
        url: 'https://api.example.com',
        body: 'raw string body',
      },
    }

    renderTaskNodeDetails(taskData, 'task-api-string-body')

    expect(screen.getByTestId('action-node-form')).toBeInTheDocument()
  })

  it('shows error when updateActivity throws', async () => {
    const user = userEvent.setup()
    mockUpdateActivity.mockImplementationOnce(() => {
      throw new Error('The update failed')
    })
    const taskData = {
      type: 'script' as const,
      id: 'task-1',
      name: 'Task',
      parameters: {
        language: 'python' as const,
        code: 'print("test")',
      },
    }

    renderTaskNodeDetails(taskData, 'task-1')

    await user.click(screen.getByTestId('submit-button'))

    expect(mockShowError).toHaveBeenCalledWith({ title: 'Update failed', description: 'The update failed' })
  })

  it('shows error when updateActivity throws during API form submission', async () => {
    const user = userEvent.setup()
    mockUpdateActivity.mockImplementationOnce(() => {
      throw new Error('The update failed')
    })
    const taskData = {
      type: 'http_request' as const,
      id: 'task-api',
      name: 'API Task',
      parameters: {
        url: 'https://api.test.com',
        method: 'GET' as const,
      },
    }

    renderTaskNodeDetails(taskData, 'task-api')

    await user.click(screen.getByTestId('submit-api-button'))

    expect(mockShowError).toHaveBeenCalledWith({ title: 'Update failed', description: 'The update failed' })
  })

  it('skips header entries with empty keys when submitting', async () => {
    const user = userEvent.setup()
    const taskData = {
      type: 'http_request' as const,
      id: 'task-api',
      name: 'API Task',
      parameters: {
        method: 'GET' as const,
        url: 'https://api.example.com',
      },
    }

    renderTaskNodeDetails(taskData, 'task-api')

    await user.click(screen.getByTestId('submit-api-invalid-headers-button'))

    // Empty-key entries are silently skipped, activity still updates
    expect(mockUpdateActivity).toHaveBeenCalled()
    const updatedActivity = mockUpdateActivity.mock.calls[0][1] as { parameters: { headers?: unknown } }
    expect(updatedActivity.parameters.headers).toBeUndefined()
  })

  it('renders AAPWorkflowTemplateForm for aap_workflow_job_template task', () => {
    const taskData = {
      type: 'aap_workflow_job_template' as const,
      id: 'task-workflow',
      name: 'Workflow Task',
      parameters: {
        workflow_job_template_id: 123,
        inventory_id: 456,
        extra_vars: { env: 'production' },
      },
    }

    renderTaskNodeDetails(taskData, 'task-workflow')

    expect(screen.getByTestId('aap-workflow-template-form')).toBeInTheDocument()
  })

  it('renders AAPWorkflowTemplateForm for expression mode workflow config', () => {
    const taskData = {
      type: 'aap_workflow_job_template' as const,
      id: 'task-workflow-expr',
      name: 'Expression Workflow Task',
      parameters: {
        workflow_job_template_name: '${trigger.workflow}',
        organization_name: '${trigger.org}',
        credential_id: 'cred-xyz',
      },
    }

    renderTaskNodeDetails(taskData, 'task-workflow-expr')

    expect(screen.getByTestId('aap-workflow-template-form')).toBeInTheDocument()
  })

  it('handles undefined config gracefully', () => {
    const taskData = {
      type: 'script' as const,
      id: 'task-no-config',
      name: 'Task without config',
      // config is undefined
    } as TaskActivity

    renderTaskNodeDetails(taskData, 'task-no-config')

    expect(screen.getByTestId('action-node-form')).toBeInTheDocument()
  })

  it('handles script task with credential_id in snake_case', () => {
    const taskData = {
      type: 'script' as const,
      id: 'task-script-cred',
      name: 'Script with Credential',
      parameters: {
        language: 'python' as const,
        code: 'print("test")',
        credential_id: 'cred-456',
      },
    }

    renderTaskNodeDetails(taskData, 'task-script-cred')

    expect(screen.getByTestId('action-node-form')).toBeInTheDocument()
  })

  it('includes follow_redirects in submitted activity config', async () => {
    const user = userEvent.setup()
    const taskData = {
      type: 'http_request' as const,
      id: 'task-api-fr',
      name: 'API Task',
      parameters: {
        method: 'GET' as const,
        url: 'https://api.example.com',
      },
    }

    renderTaskNodeDetails(taskData, 'task-api-fr')

    await user.click(screen.getByTestId('submit-api-follow-redirects-button'))

    const call = mockUpdateActivity.mock.calls[0] as [string, Activity]
    expect(call[0]).toBe('task-api-fr')
    expect(call[1].parameters.follow_redirects).toBe(true)
  })

  it('handles AAP task with camelCase legacy fields', () => {
    const taskData = {
      type: 'aap_job_template' as const,
      id: 'task-aap-legacy',
      name: 'Legacy AAP Task',
      parameters: {
        jobTemplateId: 999,
        organizationId: 111,
        organization: 'Legacy Org',
        inventoryName: 'Legacy Inventory',
        extraVars: { legacy: true },
      },
    }

    renderTaskNodeDetails(taskData, 'task-aap-legacy')

    expect(screen.getByTestId('aap-node-form')).toBeInTheDocument()
  })
})
