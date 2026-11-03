import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { Node } from '@xyflow/react'
import { useEffect } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { useStepMenuActions } from '../workflows/canvas/nodes/hooks/useStepMenuActions'
import type { NodeType } from '../workflows/canvas/nodes/NodeType'

import { StepDetailsPanel } from './StepDetailsPanel'

const mockMoveActivityAfter = vi.fn()
const mockUpdateActivity = vi.fn()
const mockReplaceActivity = vi.fn()
const mockRemoveActivity = vi.fn()
const mockShowError = vi.fn()

const mockStoreState = vi.hoisted(() => ({
  currentWorkflow: { triggers: [], workflow: { activities: [] } },
}))

const mockUseWorkflowStore = vi.hoisted(() => {
  const store = vi.fn((selector?: (state: { currentWorkflow: unknown }) => unknown) => {
    const state = { currentWorkflow: mockStoreState.currentWorkflow }
    return selector ? selector(state) : state
  }) as unknown as { (selector?: (state: { currentWorkflow: unknown }) => unknown): unknown; getState: () => unknown }

  store.getState = () => ({ currentWorkflow: mockStoreState.currentWorkflow })
  return store
})

vi.mock('../../stores/useWorkflowStore', async (importOriginal) => {
  const original = await importOriginal<typeof import('../../stores/useWorkflowStore')>()
  return {
    ...original,
    useWorkflowStore: mockUseWorkflowStore,
    useWorkflowStoreActions: vi.fn(() => ({
      moveActivityAfter: mockMoveActivityAfter,
      updateActivity: mockUpdateActivity,
      replaceActivity: mockReplaceActivity,
      removeActivity: mockRemoveActivity,
    })),
    selectCurrentWorkflow: (state: { currentWorkflow: unknown }) => state.currentWorkflow,
  }
})

vi.mock('../../providers/alerts', () => ({
  useAlerts: vi.fn(() => ({
    showError: mockShowError,
  })),
}))

const { mockStepRegistryGetAll, mockStepRegistryGet, taskDetailsMountCount } = vi.hoisted(() => ({
  mockStepRegistryGetAll: vi.fn(),
  mockStepRegistryGet: vi.fn(),
  taskDetailsMountCount: { current: 0 },
}))

vi.mock('./registry/StepRegistry', () => ({
  StepRegistry: {
    getAll: mockStepRegistryGetAll,
    get: mockStepRegistryGet,
  },
}))

vi.mock('./step-details', () => ({
  TaskStepDetails: ({ nodeId }: { nodeId: string }) => {
    useEffect(() => {
      taskDetailsMountCount.current += 1
    }, [])
    return <div data-testid="task-details">{nodeId}</div>
  },
  ApprovalStepDetails: () => <div data-testid="approval-details" />,
  ConditionStepDetails: () => <div data-testid="condition-details" />,
  LoopStepDetails: () => <div data-testid="loop-details" />,
  ConvergeStepDetails: () => <div data-testid="converge-details" />,
  TriggerStepDetails: () => <div data-testid="trigger-details" />,
}))

vi.mock('./StepRawDataView', () => ({
  StepRawDataView: () => <div data-testid="raw-node-view" />,
}))

vi.mock('./panels/hooks/useAdjacentSteps', () => ({
  useAdjacentSteps: vi.fn(() => ({ upstream: [], downstream: [] })),
}))

vi.mock('./panels/hooks/useStepExecutionData', () => ({
  useStepExecutionData: vi.fn(() => ({ inputData: null, outputData: null, isLoading: false })),
}))

vi.mock('./panels/InputPanel', () => ({
  InputPanel: () => <div data-testid="input-panel">Input</div>,
}))

vi.mock('./panels/OutputPanel', () => ({
  OutputPanel: () => <div data-testid="output-panel">Output</div>,
}))

vi.mock('../workflows/canvas/nodes/hooks/useStepMenuActions', () => ({
  useStepMenuActions: vi.fn(() => []),
  StepMenuCategory: { ACTIVITY: 'activity', TRIGGER: 'trigger' },
}))

vi.mock('../../components/steps/SynStepMenu', () => ({
  SynStepMenu: ({ menuActions }: { menuActions: Array<{ onClick: () => void }> }) => (
    <button onClick={() => menuActions[0]?.onClick()} type="button">
      Menu
    </button>
  ),
}))

describe('StepDetailsPanel', () => {
  const mockOnClose = vi.fn()

  beforeEach(() => {
    vi.clearAllMocks()
    taskDetailsMountCount.current = 0
    mockStoreState.currentWorkflow = { triggers: [], workflow: { activities: [] } }
    mockStepRegistryGetAll.mockReturnValue([] as never)
  })

  it('renders add mode form and closes on submit', async () => {
    const user = userEvent.setup()
    const mockOnSubmit = vi.fn((_data, onSuccess: (nodeId?: string) => void) => onSuccess('node-1'))

    mockStepRegistryGet.mockReturnValue({
      id: 'action',
      label: 'Action',
      icon: () => <div>ActionIcon</div>,
      category: 'task',
      formComponent: ({ onSubmit }: { onSubmit: (data: Record<string, unknown>) => void }) => (
        <button onClick={() => onSubmit({})} type="button">
          Submit
        </button>
      ),
      onSubmit: mockOnSubmit,
    })

    render(<StepDetailsPanel mode="add" stepTypeId="action" stepSubtypeId={null} onClose={mockOnClose} />)

    await user.click(screen.getByRole('button', { name: /Submit/i }))

    expect(mockOnClose).toHaveBeenCalled()
  })

  it('updates replacement node when new node is created', async () => {
    const user = userEvent.setup()
    const mockOnSubmit = vi.fn((_data, onSuccess: (nodeId?: string) => void) => onSuccess('new-1'))

    mockStoreState.currentWorkflow = {
      triggers: [],
      workflow: {
        activities: [
          {
            id: 'new-1',
            type: 'task',
            name: 'New Task',
            task: { executor: 'script', parameters: {} },
            metadata: { __isGeneric: true, __customMessage: 'test message' },
          },
        ],
      },
    } as never

    mockStepRegistryGet.mockReturnValue({
      id: 'action',
      label: 'Action',
      icon: () => <div>ActionIcon</div>,
      category: 'task',
      formComponent: ({ onSubmit }: { onSubmit: (data: Record<string, unknown>) => void }) => (
        <button onClick={() => onSubmit({})} type="button">
          Submit
        </button>
      ),
      onSubmit: mockOnSubmit,
    })

    render(
      <StepDetailsPanel
        mode="add"
        stepTypeId="action"
        stepSubtypeId={null}
        replacementNodeId="replacement-1"
        onClose={mockOnClose}
      />
    )

    await user.click(screen.getByRole('button', { name: /Submit/i }))

    expect(mockRemoveActivity).toHaveBeenCalledWith('new-1')
    expect(mockReplaceActivity).toHaveBeenCalledWith(
      'replacement-1',
      expect.objectContaining({
        id: 'replacement-1',
        // __isGeneric is removed by cleanMetadata before replaceActivity is called
        metadata: { __customMessage: 'test message' },
      })
    )
  })

  it('clears metadata when replacement node update has no new node id', async () => {
    const user = userEvent.setup()
    const mockOnSubmit = vi.fn((_data, onSuccess: (nodeId?: string) => void) => onSuccess())

    mockStoreState.currentWorkflow = {
      triggers: [],
      workflow: {
        activities: [
          {
            id: 'replacement-1',
            type: 'task',
            name: 'Replacement Task',
            task: { executor: 'script', parameters: {} },
            metadata: { __isGeneric: true },
          },
        ],
      },
    } as never

    mockStepRegistryGet.mockReturnValue({
      id: 'action',
      label: 'Action',
      icon: () => <div>ActionIcon</div>,
      category: 'task',
      formComponent: ({ onSubmit }: { onSubmit: (data: Record<string, unknown>) => void }) => (
        <button onClick={() => onSubmit({})} type="button">
          Submit
        </button>
      ),
      onSubmit: mockOnSubmit,
    })

    render(
      <StepDetailsPanel
        mode="add"
        stepTypeId="action"
        stepSubtypeId={null}
        replacementNodeId="replacement-1"
        onClose={mockOnClose}
      />
    )

    await user.click(screen.getByRole('button', { name: /Submit/i }))

    expect(mockUpdateActivity).toHaveBeenCalledWith(
      'replacement-1',
      expect.objectContaining({
        metadata: undefined,
      })
    )
  })

  it('shows error when add step fails', async () => {
    const user = userEvent.setup()
    const mockOnSubmit = vi.fn((_data, _onSuccess, onError: (error: string) => void) => onError('boom'))

    mockStepRegistryGet.mockReturnValue({
      id: 'action',
      label: 'Action',
      icon: () => <div>ActionIcon</div>,
      category: 'task',
      formComponent: ({ onSubmit }: { onSubmit: (data: Record<string, unknown>) => void }) => (
        <button onClick={() => onSubmit({})} type="button">
          Submit
        </button>
      ),
      onSubmit: mockOnSubmit,
    })

    render(<StepDetailsPanel mode="add" stepTypeId="action" stepSubtypeId={null} onClose={mockOnClose} />)

    await user.click(screen.getByRole('button', { name: /Submit/i }))

    expect(mockShowError).toHaveBeenCalledWith({ title: 'Add step failed', description: 'boom' })
    expect(mockOnClose).not.toHaveBeenCalled()
  })

  it('resolves add-mode submit as failed when registry onSubmit never callbacks', async () => {
    const user = userEvent.setup()
    const mockOnSubmit = vi.fn()
    const onFormSettled = vi.fn()

    mockStepRegistryGet.mockReturnValue({
      id: 'action',
      label: 'Action',
      icon: () => <div>ActionIcon</div>,
      category: 'task',
      formComponent: ({ onSubmit }: { onSubmit: (data: Record<string, unknown>) => Promise<boolean> }) => (
        <button
          onClick={async () => {
            onFormSettled(await onSubmit({}))
          }}
          type="button"
        >
          Submit
        </button>
      ),
      onSubmit: mockOnSubmit,
    })

    render(<StepDetailsPanel mode="add" stepTypeId="action" stepSubtypeId={null} onClose={mockOnClose} />)

    await user.click(screen.getByRole('button', { name: /Submit/i }))

    await waitFor(() => {
      expect(onFormSettled).toHaveBeenCalledWith(false)
    })
    expect(mockOnClose).not.toHaveBeenCalled()
  })

  it('moves and connects new node when adding from an edge', async () => {
    const user = userEvent.setup()
    const mockOnSubmit = vi.fn((_data, onSuccess: (nodeId?: string) => void) => onSuccess('node-2'))
    const mockOnConnect = vi.fn()

    mockStepRegistryGet.mockReturnValue({
      id: 'action',
      label: 'Action',
      icon: () => <div>ActionIcon</div>,
      category: 'task',
      formComponent: ({ onSubmit }: { onSubmit: (data: Record<string, unknown>) => void }) => (
        <button onClick={() => onSubmit({})} type="button">
          Submit
        </button>
      ),
      onSubmit: mockOnSubmit,
    })

    render(
      <StepDetailsPanel
        mode="add"
        stepTypeId="action"
        stepSubtypeId={null}
        sourceNodeId="node-1"
        onConnect={mockOnConnect}
        onClose={mockOnClose}
      />
    )

    await user.click(screen.getByRole('button', { name: /Submit/i }))

    expect(mockMoveActivityAfter).toHaveBeenCalledWith('node-2', 'node-1')
    expect(mockOnConnect).toHaveBeenCalledWith('node-1', 'node-2')
    expect(mockOnClose).toHaveBeenCalled()
  })

  it('closes when the cancel button is clicked in add mode', async () => {
    const user = userEvent.setup()

    mockStepRegistryGet.mockReturnValue({
      id: 'action',
      label: 'Action',
      icon: () => <div>ActionIcon</div>,
      category: 'task',
      formComponent: () => <div>Form</div>,
      onSubmit: vi.fn(),
    })

    render(<StepDetailsPanel mode="add" stepTypeId="action" stepSubtypeId={null} onClose={mockOnClose} />)

    await user.click(screen.getByRole('button', { name: /Cancel step creation/i }))

    expect(mockOnClose).toHaveBeenCalled()
  })

  it('renders task details in edit mode', () => {
    const taskNode: Node<NodeType['data']> = {
      id: 'task-1',
      type: 'task',
      position: { x: 0, y: 0 },
      data: { id: 'task-1', type: 'task', name: 'Task', task: { executor: 'script', parameters: {} } },
    }

    render(<StepDetailsPanel mode="edit" node={taskNode} onClose={mockOnClose} />)

    expect(screen.getByTestId('task-details')).toBeInTheDocument()
  })

  it('renders trigger details in edit mode when trigger exists', () => {
    mockStoreState.currentWorkflow = { triggers: [{ type: 'manual' }], workflow: { activities: [] } } as never
    const triggerNode: Node<NodeType['data']> = {
      id: 'trigger-0',
      type: 'trigger',
      position: { x: 0, y: 0 },
      data: { id: 'trigger-0', type: 'trigger', name: 'Trigger' },
    }

    render(<StepDetailsPanel mode="edit" node={triggerNode} onClose={mockOnClose} />)

    expect(screen.getByTestId('trigger-details')).toBeInTheDocument()
    expect(screen.queryByText('Input')).not.toBeInTheDocument()
  })

  it('renders menu actions in edit mode and closes on delete', async () => {
    const user = userEvent.setup()
    const deleteAction = vi.fn()

    vi.mocked(useStepMenuActions).mockReturnValueOnce([
      { id: 'delete', label: 'Delete', onClick: deleteAction, variant: 'danger' as const },
    ])

    const taskNode: Node<NodeType['data']> = {
      id: 'task-1',
      type: 'task',
      position: { x: 0, y: 0 },
      data: { id: 'task-1', type: 'task', name: 'Task', task: { executor: 'script', parameters: {} } },
    }

    render(<StepDetailsPanel mode="edit" node={taskNode} onClose={mockOnClose} />)

    await user.click(screen.getByRole('button', { name: /menu/i }))

    expect(deleteAction).toHaveBeenCalledTimes(1)
    expect(mockOnClose).toHaveBeenCalledTimes(1)
  })

  it.each([
    ['condition', 'condition-details'],
    ['loop', 'loop-details'],
    ['converge', 'converge-details'],
    ['approval', 'approval-details'],
  ])('renders %s details in edit mode', (nodeType, testId) => {
    const nodeMap: Record<string, Node<NodeType['data']>> = {
      condition: {
        id: 'condition-1',
        type: 'condition',
        position: { x: 0, y: 0 },
        data: { id: 'condition-1', type: 'condition', name: 'Condition', condition: 'true' },
      },
      loop: {
        id: 'loop-1',
        type: 'loop',
        position: { x: 0, y: 0 },
        data: { id: 'loop-1', type: 'loop', name: 'Loop', loop: { type: 'forEach', items: 'x', do: [] } },
      },
      converge: {
        id: 'converge-1',
        type: 'converge',
        position: { x: 0, y: 0 },
        data: {
          id: 'converge-1',
          type: 'converge',
          name: 'Converge',
          converge: { branches: [], strategy: 'all' },
        },
      },
      approval: {
        id: 'approval-1',
        type: 'approval',
        position: { x: 0, y: 0 },
        data: {
          id: 'approval-1',
          type: 'approval',
          name: 'Approval',
          task: { executor: 'approval', parameters: {} },
        },
      },
    }

    render(<StepDetailsPanel mode="edit" node={nodeMap[nodeType]} onClose={mockOnClose} />)
    expect(screen.getByTestId(testId)).toBeInTheDocument()
  })

  it('renders raw data view for unknown step types', () => {
    const unknownNode = {
      id: 'unknown-1',
      type: 'email',
      position: { x: 0, y: 0 },
      data: { id: 'unknown-1', type: 'email', name: 'Email' },
    } as unknown as Node<NodeType['data']>

    render(<StepDetailsPanel mode="edit" node={unknownNode} onClose={mockOnClose} />)

    expect(screen.getByTestId('raw-node-view')).toBeInTheDocument()
  })

  it('hides input panel when adding a trigger', () => {
    mockStepRegistryGet.mockReturnValue({
      id: 'trigger',
      label: 'Trigger',
      icon: () => <div>TriggerIcon</div>,
      category: 'trigger',
      formComponent: () => <div>Form</div>,
      onSubmit: vi.fn(),
    })

    render(<StepDetailsPanel mode="add" stepTypeId="trigger" stepSubtypeId={null} onClose={mockOnClose} />)

    expect(screen.queryByText('Input')).not.toBeInTheDocument()
  })

  it('shows error when replacement fails due to new activity not found', async () => {
    const user = userEvent.setup()
    const mockOnSubmit = vi.fn((_data, onSuccess: (nodeId?: string) => void) => onSuccess('new-1'))
    let submitOutcome: boolean | void

    // Empty activities - the new-1 activity doesn't exist
    mockStoreState.currentWorkflow = {
      triggers: [],
      workflow: {
        activities: [],
      },
    }

    mockStepRegistryGet.mockReturnValue({
      id: 'action',
      label: 'Action',
      icon: () => <div>ActionIcon</div>,
      category: 'task',
      formComponent: ({
        onSubmit,
      }: {
        onSubmit: (data: Record<string, unknown>) => Promise<boolean> | boolean | void
      }) => (
        <button
          onClick={async () => {
            submitOutcome = await onSubmit({})
          }}
          type="button"
        >
          Submit
        </button>
      ),
      onSubmit: mockOnSubmit,
    })

    render(
      <StepDetailsPanel
        mode="add"
        stepTypeId="action"
        stepSubtypeId={null}
        replacementNodeId="replacement-1"
        onClose={mockOnClose}
      />
    )

    await user.click(screen.getByRole('button', { name: /Submit/i }))

    await waitFor(() => {
      expect(submitOutcome).toBe(false)
    })
    expect(mockShowError).toHaveBeenCalledWith({
      title: 'Replacement failed',
      description: 'Failed to replace step — step not found',
    })
    expect(mockOnClose).not.toHaveBeenCalled()
  })

  it('shows error when replacement update fails due to activity not found', async () => {
    const user = userEvent.setup()
    const mockOnSubmit = vi.fn((_data, onSuccess: (nodeId?: string) => void) => onSuccess())
    let submitOutcome: boolean | void

    mockStoreState.currentWorkflow = {
      triggers: [],
      workflow: {
        activities: [],
      },
    }

    mockStepRegistryGet.mockReturnValue({
      id: 'action',
      label: 'Action',
      icon: () => <div>ActionIcon</div>,
      category: 'task',
      formComponent: ({
        onSubmit,
      }: {
        onSubmit: (data: Record<string, unknown>) => Promise<boolean> | boolean | void
      }) => (
        <button
          onClick={async () => {
            submitOutcome = await onSubmit({})
          }}
          type="button"
        >
          Submit
        </button>
      ),
      onSubmit: mockOnSubmit,
    })

    render(
      <StepDetailsPanel
        mode="add"
        stepTypeId="action"
        stepSubtypeId={null}
        replacementNodeId="missing-node"
        onClose={mockOnClose}
      />
    )

    await user.click(screen.getByRole('button', { name: /Submit/i }))

    await waitFor(() => {
      expect(submitOutcome).toBe(false)
    })
    expect(mockShowError).toHaveBeenCalledWith({
      title: 'Replacement failed',
      description: 'Failed to replace step — step not found',
    })
    expect(mockOnClose).not.toHaveBeenCalled()
  })

  it('renders form for node with subtypes', async () => {
    const user = userEvent.setup()
    const mockOnSubmit = vi.fn((_data, onSuccess: (nodeId?: string) => void) => onSuccess('node-1'))

    mockStepRegistryGet.mockReturnValue({
      id: 'logic',
      label: 'Logic',
      icon: () => <div>LogicIcon</div>,
      category: 'logic',
      subtypes: [
        {
          id: 'condition',
          label: 'Condition',
          formComponent: ({ onSubmit }: { onSubmit: (data: Record<string, unknown>) => void }) => (
            <button onClick={() => onSubmit({})} type="button">
              Submit Condition
            </button>
          ),
          formProps: { testProp: 'value' },
          initialData: { type: 'condition', condition: 'true' },
        },
      ],
      formComponent: ({ onSubmit }: { onSubmit: (data: Record<string, unknown>) => void }) => (
        <button onClick={() => onSubmit({})} type="button">
          Submit Logic
        </button>
      ),
      onSubmit: mockOnSubmit,
    })

    render(<StepDetailsPanel mode="add" stepTypeId="logic" stepSubtypeId="condition" onClose={mockOnClose} />)

    // Should use subtype's form component
    expect(screen.getByRole('button', { name: /Submit Condition/i })).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /Submit Condition/i }))

    expect(mockOnClose).toHaveBeenCalled()
  })

  it('uses subtype label and initial data when available', () => {
    mockStepRegistryGet.mockReturnValue({
      id: 'aap',
      label: 'AAP',
      icon: () => <div>AAPIcon</div>,
      category: 'task',
      subtypes: [
        {
          id: 'job_template',
          label: 'Job Template',
          formComponent: () => <div>Job Template Form</div>,
          initialData: { executor: 'aap_job_template' },
        },
      ],
      formComponent: () => <div>AAP Form</div>,
      onSubmit: vi.fn(),
    })

    render(<StepDetailsPanel mode="add" stepTypeId="aap" stepSubtypeId="job_template" onClose={mockOnClose} />)

    expect(screen.getByText('Job Template Form')).toBeInTheDocument()
  })

  it('renders empty parameters when selected node is not found in add mode', () => {
    mockStepRegistryGet.mockReturnValue(null)

    render(<StepDetailsPanel mode="add" stepTypeId="unknown" stepSubtypeId={null} onClose={mockOnClose} />)

    // Should render panel layout even when node type not found (empty parameters content)
    // The panel itself will be shown, but the content area will be empty
    expect(screen.getByRole('button', { name: /Cancel step creation/i })).toBeInTheDocument()
  })

  it('renders trigger form in add mode', () => {
    mockStepRegistryGet.mockReturnValue({
      id: 'trigger',
      label: 'Trigger',
      icon: () => <div>TriggerIcon</div>,
      category: 'trigger',
      formComponent: () => <div data-testid="trigger-form">Trigger Form</div>,
      onSubmit: vi.fn(),
    })

    render(<StepDetailsPanel mode="add" stepTypeId="trigger" stepSubtypeId={null} onClose={mockOnClose} />)

    expect(screen.getByTestId('trigger-form')).toBeInTheDocument()
  })

  it('does not render input panel when editing trigger', () => {
    mockStoreState.currentWorkflow = { triggers: [{ type: 'manual' }], workflow: { activities: [] } } as never
    const triggerNode: Node<NodeType['data']> = {
      id: 'trigger-0',
      type: 'trigger',
      position: { x: 0, y: 0 },
      data: { id: 'trigger-0', type: 'trigger', name: 'Trigger' },
    }

    render(<StepDetailsPanel mode="edit" node={triggerNode} onClose={mockOnClose} />)

    expect(screen.queryByTestId('input-panel')).not.toBeInTheDocument()
  })

  it('passes projectId to form component', () => {
    mockStepRegistryGet.mockReturnValue({
      id: 'action',
      label: 'Action',
      icon: () => <div>ActionIcon</div>,
      category: 'task',
      formComponent: ({ projectId }: { projectId?: string }) => (
        <div data-testid="project-id">{projectId ?? 'none'}</div>
      ),
      onSubmit: vi.fn(),
    })

    render(
      <StepDetailsPanel
        mode="add"
        stepTypeId="action"
        stepSubtypeId={null}
        projectId="project-123"
        onClose={mockOnClose}
      />
    )

    expect(screen.getByTestId('project-id')).toHaveTextContent('project-123')
  })

  it('passes executionId and workflowId to StepEditorLayout', () => {
    const taskNode: Node<NodeType['data']> = {
      id: 'task-1',
      type: 'task',
      position: { x: 0, y: 0 },
      data: { id: 'task-1', type: 'task', name: 'Task', task: { executor: 'script', parameters: {} } },
    }

    render(
      <StepDetailsPanel
        mode="edit"
        node={taskNode}
        executionId="exec-123"
        workflowId="workflow-456"
        onClose={mockOnClose}
      />
    )

    // StepEditorLayout receives these props and passes them to panels
    expect(screen.getByTestId('task-details')).toBeInTheDocument()
  })

  it('remounts task details when navigating to a different node id', () => {
    const makeTaskNode = (id: string): Node<NodeType['data']> => ({
      id,
      type: 'task',
      position: { x: 0, y: 0 },
      data: { id, type: 'script', name: id, parameters: { language: 'python', code: '' } },
    })

    const { rerender } = render(
      <StepDetailsPanel mode="edit" node={makeTaskNode('check-value')} onClose={mockOnClose} />
    )

    expect(screen.getByTestId('task-details')).toHaveTextContent('check-value')
    expect(taskDetailsMountCount.current).toBe(1)

    rerender(<StepDetailsPanel mode="edit" node={makeTaskNode('positive-branch')} onClose={mockOnClose} />)

    expect(screen.getByTestId('task-details')).toHaveTextContent('positive-branch')
    expect(taskDetailsMountCount.current).toBe(2)
  })
})
