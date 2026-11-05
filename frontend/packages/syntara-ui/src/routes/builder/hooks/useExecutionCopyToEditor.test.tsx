import { act, renderHook } from '@testing-library/react'
import { describe, expect, it, vi, beforeEach } from 'vitest'

import { useWorkflowStore } from '../../../stores/useWorkflowStore'

import type { ExecutionCopyData } from './useExecutionCopyToEditor'
import { useExecutionCopyToEditor } from './useExecutionCopyToEditor'

vi.mock('../utils/parseImportedDefinition', () => ({
  parseImportedDefinition: vi.fn((def: Record<string, unknown>) => ({
    workflowDef: {
      name: def.name ?? 'parsed-wf',
      description: def.description ?? '',
      workflow: { activities: [{ id: 'copied-task-1' }, { id: 'copied-cond-1' }] },
      triggers: [{ id: 'copied-trigger-1' }],
    },
    edges: [],
    nodePositions: {},
  })),
}))

function buildOptions(overrides: Partial<Parameters<typeof useExecutionCopyToEditor>[0]> = {}) {
  return {
    executionCopy: undefined as ExecutionCopyData | undefined,
    dispatch: vi.fn(),
    markDirty: vi.fn(),
    showSuccess: vi.fn(),
    ...overrides,
  }
}

function buildExecutionCopy(overrides: Partial<ExecutionCopyData> = {}): ExecutionCopyData {
  return {
    executionId: 'exec-123',
    workflowDefinition: { name: 'test-wf', description: 'desc', nodes: [], triggers: [], edges: [] },
    ...overrides,
  }
}

async function renderAndApply(opts: ReturnType<typeof buildOptions>) {
  const view = renderHook(() => useExecutionCopyToEditor(opts))
  await act(async () => {
    await Promise.resolve()
    view.result.current()
  })
  return view
}

describe('useExecutionCopyToEditor', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useWorkflowStore.getState().setWorkflow({
      schema_version: '2.0.0',
      name: 'existing',
      description: '',
      workflow: { activities: [] },
    })
    vi.spyOn(window.history, 'replaceState').mockImplementation(() => {})
  })

  it('does nothing when executionCopy is undefined', async () => {
    const opts = buildOptions()
    await renderAndApply(opts)
    expect(opts.dispatch).not.toHaveBeenCalled()
    expect(opts.showSuccess).not.toHaveBeenCalled()
  })

  it('does nothing when currentWorkflow is null', async () => {
    useWorkflowStore.getState().setWorkflow(null)
    const opts = buildOptions({ executionCopy: buildExecutionCopy() })
    await renderAndApply(opts)
    expect(opts.dispatch).not.toHaveBeenCalled()
  })

  it('calls replaceWorkflowContent with parsed definition', async () => {
    const replaceSpy = vi.spyOn(useWorkflowStore.getState(), 'replaceWorkflowContent')
    const opts = buildOptions({ executionCopy: buildExecutionCopy() })
    await renderAndApply(opts)
    expect(replaceSpy).toHaveBeenCalledOnce()
  })

  it('dispatches SET_WORKFLOW_NAME from parsed definition', async () => {
    const opts = buildOptions({ executionCopy: buildExecutionCopy() })
    await renderAndApply(opts)
    expect(opts.dispatch).toHaveBeenCalledWith(expect.objectContaining({ type: 'SET_WORKFLOW_NAME' }) as unknown)
  })

  it('dispatches SET_MOST_RECENT_EXECUTION with execution ID and copied activity allowlist', async () => {
    const opts = buildOptions({ executionCopy: buildExecutionCopy({ executionId: 'exec-abc' }) })
    await renderAndApply(opts)
    expect(opts.dispatch).toHaveBeenCalledWith({
      type: 'SET_MOST_RECENT_EXECUTION',
      payload: {
        executionId: 'exec-abc',
        copiedRunActivityIds: ['copied-task-1', 'copied-cond-1', 'copied-trigger-1'],
      },
    })
  })

  it('calls markDirty', async () => {
    const opts = buildOptions({ executionCopy: buildExecutionCopy() })
    await renderAndApply(opts)
    expect(opts.markDirty).toHaveBeenCalledOnce()
  })

  it('shows success toast', async () => {
    const opts = buildOptions({ executionCopy: buildExecutionCopy() })
    await renderAndApply(opts)
    expect(opts.showSuccess).toHaveBeenCalledWith({
      title: 'Run copied to editor',
      description: 'The run has been loaded into the editor with pinned runtime data.',
    })
  })

  it('cleans the URL query params', async () => {
    const replaceStateSpy = vi.spyOn(window.history, 'replaceState')
    const opts = buildOptions({ executionCopy: buildExecutionCopy() })
    await renderAndApply(opts)
    expect(replaceStateSpy).toHaveBeenCalledWith({}, '', window.location.pathname)
  })

  it('applies only once even on re-render', async () => {
    const opts = buildOptions({ executionCopy: buildExecutionCopy() })
    const { result, rerender } = renderHook(() => useExecutionCopyToEditor(opts))
    await act(async () => {
      await Promise.resolve()
      result.current()
    })
    rerender()
    rerender()
    await act(async () => {
      await Promise.resolve()
      result.current()
    })
    expect(opts.showSuccess).toHaveBeenCalledOnce()
  })

  describe('preserveWorkflow mode', () => {
    it('skips content replacement when preserveWorkflow is true', async () => {
      const replaceSpy = vi.spyOn(useWorkflowStore.getState(), 'replaceWorkflowContent')
      const opts = buildOptions({ executionCopy: buildExecutionCopy({ preserveWorkflow: true }) })
      await renderAndApply(opts)
      expect(replaceSpy).not.toHaveBeenCalled()
    })

    it('does not overwrite workflow name when preserveWorkflow is true', async () => {
      const dispatch = vi.fn()
      const opts = buildOptions({ dispatch, executionCopy: buildExecutionCopy({ preserveWorkflow: true }) })
      await renderAndApply(opts)
      expect(dispatch).not.toHaveBeenCalledWith(expect.objectContaining({ type: 'SET_WORKFLOW_NAME' }) as unknown)
    })

    it('still dispatches SET_MOST_RECENT_EXECUTION when preserveWorkflow is true', async () => {
      useWorkflowStore.getState().setWorkflow({
        schema_version: '2.0.0',
        name: 'existing',
        description: '',
        workflow: { activities: [{ id: 'existing-task' } as never] },
        triggers: [{ id: 'existing-trigger' } as never],
      })
      const opts = buildOptions({
        executionCopy: buildExecutionCopy({ executionId: 'exec-fork', preserveWorkflow: true }),
      })
      await renderAndApply(opts)
      expect(opts.dispatch).toHaveBeenCalledWith({
        type: 'SET_MOST_RECENT_EXECUTION',
        payload: {
          executionId: 'exec-fork',
          copiedRunActivityIds: ['existing-task', 'existing-trigger'],
        },
      })
    })

    it('does not mark dirty or show toast when preserveWorkflow is true', async () => {
      const opts = buildOptions({ executionCopy: buildExecutionCopy({ preserveWorkflow: true }) })
      await renderAndApply(opts)
      expect(opts.markDirty).not.toHaveBeenCalled()
      expect(opts.showSuccess).not.toHaveBeenCalled()
    })
  })
})
