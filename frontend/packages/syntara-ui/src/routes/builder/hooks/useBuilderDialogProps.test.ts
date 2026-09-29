import { describe, expect, it, vi } from 'vitest'

import type { BuilderDialogPropsParams } from './useBuilderDialogProps'
import { useBuilderDialogProps } from './useBuilderDialogProps'

function makeParams(overrides: Partial<BuilderDialogPropsParams> = {}): BuilderDialogPropsParams {
  return {
    workflowName: 'test',
    workflowId: 'wf-1',
    confirmDialogOpen: false,
    deleteDialogOpen: false,
    selectedTriggerIndex: 0,
    currentWorkflow: null,
    dispatch: vi.fn(),
    handleRunWorkflow: vi.fn(),
    handleDeleteWorkflow: vi.fn(),
    isDeleting: false,
    runStepDialog: { isOpen: false, open: vi.fn(), close: vi.fn(), item: null },
    lastRunStepNodeIdRef: { current: null },
    pendingImport: null,
    setPendingImport: vi.fn(),
    selectedProject: null,
    createWorkflow: vi.fn() as BuilderDialogPropsParams['createWorkflow'],
    setLocation: vi.fn(),
    pinnedMockDataForDialog: undefined,
    ...overrides,
  }
}

describe('useBuilderDialogProps — isDeleting', () => {
  it('passes isDeleting through to dialog props', () => {
    const result = useBuilderDialogProps(makeParams({ isDeleting: true }))

    expect(result.isDeleting).toBe(true)
  })
})

describe('useBuilderDialogProps — runStepTriggerNodeId', () => {
  it('maps trigger-0 predecessor to the first trigger definition ID', () => {
    const params = makeParams({
      currentWorkflow: {
        triggers: [{ id: 'def-trigger-1', type: 'manual_trigger', parameters: {} }],
      },
      runStepDialog: {
        isOpen: true,
        open: vi.fn(),
        close: vi.fn(),
        item: {
          nodeId: 'step-a',
          nodeName: 'Step A',
          predecessors: [{ id: 'trigger-0', name: 'Trigger', isTrigger: true }],
        },
      },
    })

    const result = useBuilderDialogProps(params)

    expect(result.runStepTriggerNodeId).toBe('def-trigger-1')
  })

  it('maps trigger-1 predecessor to the second trigger definition ID', () => {
    const params = makeParams({
      currentWorkflow: {
        triggers: [
          { id: 'def-trigger-1', type: 'manual_trigger', parameters: {} },
          { id: 'def-trigger-2', type: 'webhook_trigger', parameters: {} },
        ],
      },
      runStepDialog: {
        isOpen: true,
        open: vi.fn(),
        close: vi.fn(),
        item: {
          nodeId: 'step-b',
          nodeName: 'Step B',
          predecessors: [{ id: 'trigger-1', name: 'Trigger 2', isTrigger: true }],
        },
      },
    })

    const result = useBuilderDialogProps(params)

    expect(result.runStepTriggerNodeId).toBe('def-trigger-2')
  })

  it('returns undefined when no trigger predecessor exists', () => {
    const params = makeParams({
      currentWorkflow: {
        triggers: [{ id: 'def-trigger-1', type: 'manual_trigger', parameters: {} }],
      },
      runStepDialog: {
        isOpen: true,
        open: vi.fn(),
        close: vi.fn(),
        item: {
          nodeId: 'step-a',
          nodeName: 'Step A',
          predecessors: [{ id: 'node-x', name: 'Node X' }],
        },
      },
    })

    const result = useBuilderDialogProps(params)

    expect(result.runStepTriggerNodeId).toBeUndefined()
  })

  it('returns undefined when run step dialog is closed', () => {
    const params = makeParams({
      currentWorkflow: {
        triggers: [{ id: 'def-trigger-1', type: 'manual_trigger', parameters: {} }],
      },
    })

    const result = useBuilderDialogProps(params)

    expect(result.runStepTriggerNodeId).toBeUndefined()
  })
})
