import { renderHook, waitFor } from '@testing-library/react'
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
    isWorkflowInitialized: true,
    mostRecentExecutionId: null as string | null,
    mostRecentRunPanelOpen: false,
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

  it('does nothing when executionCopy is undefined', () => {
    const opts = buildOptions()
    renderHook(() => useExecutionCopyToEditor(opts))
    expect(opts.dispatch).not.toHaveBeenCalled()
    expect(opts.showSuccess).not.toHaveBeenCalled()
  })

  it('does nothing when currentWorkflow is null', () => {
    useWorkflowStore.getState().setWorkflow(null)
    const opts = buildOptions({ executionCopy: buildExecutionCopy() })
    renderHook(() => useExecutionCopyToEditor(opts))
    expect(opts.dispatch).not.toHaveBeenCalled()
  })

  it('does nothing until workflow initialization completes', () => {
    const opts = buildOptions({ executionCopy: buildExecutionCopy(), isWorkflowInitialized: false })
    renderHook(() => useExecutionCopyToEditor(opts))
    expect(opts.dispatch).not.toHaveBeenCalled()
  })

  it('calls replaceWorkflowContent with parsed definition', async () => {
    const replaceSpy = vi.spyOn(useWorkflowStore.getState(), 'replaceWorkflowContent')
    const opts = buildOptions({ executionCopy: buildExecutionCopy() })
    renderHook(() => useExecutionCopyToEditor(opts))
    await waitFor(() => expect(replaceSpy).toHaveBeenCalledOnce())
  })

  it('dispatches SET_WORKFLOW_NAME from parsed definition', async () => {
    const opts = buildOptions({ executionCopy: buildExecutionCopy() })
    renderHook(() => useExecutionCopyToEditor(opts))
    await waitFor(() =>
      expect(opts.dispatch).toHaveBeenCalledWith(expect.objectContaining({ type: 'SET_WORKFLOW_NAME' }) as unknown)
    )
  })

  it('dispatches SET_MOST_RECENT_EXECUTION with execution ID and copied activity allowlist', async () => {
    const opts = buildOptions({ executionCopy: buildExecutionCopy({ executionId: 'exec-abc' }) })
    renderHook(() => useExecutionCopyToEditor(opts))
    await waitFor(() =>
      expect(opts.dispatch).toHaveBeenCalledWith({
        type: 'SET_MOST_RECENT_EXECUTION',
        payload: {
          executionId: 'exec-abc',
          copiedRunActivityIds: ['copied-task-1', 'copied-cond-1', 'copied-trigger-1'],
        },
      })
    )
  })

  it('calls markDirty', async () => {
    const opts = buildOptions({ executionCopy: buildExecutionCopy() })
    renderHook(() => useExecutionCopyToEditor(opts))
    await waitFor(() => expect(opts.markDirty).toHaveBeenCalledOnce())
  })

  it('shows success toast', async () => {
    const opts = buildOptions({ executionCopy: buildExecutionCopy() })
    renderHook(() => useExecutionCopyToEditor(opts))
    await waitFor(() =>
      expect(opts.showSuccess).toHaveBeenCalledWith({
        title: 'Run copied to editor',
        description: 'The run has been loaded into the editor with pinned runtime data.',
      })
    )
  })

  it('cleans the URL query params after reducer syncs', async () => {
    Object.defineProperty(window, 'location', {
      configurable: true,
      value: new URL('https://localhost/workflow-builder/wf-1?fromExecution=exec-123'),
    })
    const replaceStateSpy = vi.spyOn(window.history, 'replaceState')
    const opts = buildOptions({
      executionCopy: buildExecutionCopy({ executionId: 'exec-123' }),
      mostRecentExecutionId: 'exec-123',
      mostRecentRunPanelOpen: true,
    })
    renderHook(() => useExecutionCopyToEditor(opts))
    await waitFor(
      () => {
        expect(
          replaceStateSpy.mock.calls.some(([, , href]) => typeof href === 'string' && !href.includes('fromExecution'))
        ).toBe(true)
      },
      { timeout: 3_000 }
    )
  })

  it('applies only once even on re-render', async () => {
    const opts = buildOptions({ executionCopy: buildExecutionCopy({ executionId: 'exec-once' }) })
    const { rerender } = renderHook((p) => useExecutionCopyToEditor(p), {
      initialProps: opts,
    })
    await waitFor(() => expect(opts.showSuccess).toHaveBeenCalledOnce())
    rerender({ ...opts, mostRecentExecutionId: 'exec-once', mostRecentRunPanelOpen: true })
    rerender({ ...opts, mostRecentExecutionId: 'exec-once', mostRecentRunPanelOpen: true })
    expect(opts.showSuccess).toHaveBeenCalledOnce()
  })

  it('reopens the run panel when execution id matches but the panel was closed', async () => {
    const dispatch = vi.fn()
    const executionCopy = buildExecutionCopy({ executionId: 'exec-panel' })
    const opts = buildOptions({
      dispatch,
      executionCopy,
      mostRecentExecutionId: 'exec-panel',
      mostRecentRunPanelOpen: false,
    })
    renderHook(() => useExecutionCopyToEditor(opts))
    await waitFor(() =>
      expect(dispatch).toHaveBeenCalledWith({
        type: 'SET_MOST_RECENT_EXECUTION',
        // eslint-disable-next-line @typescript-eslint/no-unsafe-assignment -- vitest asymmetric matcher
        payload: expect.objectContaining({ executionId: 'exec-panel' }),
      })
    )
    expect(opts.showSuccess).not.toHaveBeenCalled()
  })

  it('re-dispatches run panel state when INIT cleared execution id after a replace copy', async () => {
    const dispatch = vi.fn()
    const executionCopy = buildExecutionCopy({ executionId: 'exec-retry' })
    const { rerender } = renderHook((p) => useExecutionCopyToEditor(p), {
      initialProps: buildOptions({ dispatch, executionCopy, mostRecentExecutionId: null }),
    })
    await waitFor(() =>
      expect(dispatch).toHaveBeenCalledWith({
        type: 'SET_MOST_RECENT_EXECUTION',
        // eslint-disable-next-line @typescript-eslint/no-unsafe-assignment -- vitest asymmetric matcher
        payload: expect.objectContaining({ executionId: 'exec-retry' }),
      })
    )
    dispatch.mockClear()
    rerender(buildOptions({ dispatch, executionCopy, mostRecentExecutionId: null }))
    await waitFor(() =>
      expect(dispatch).toHaveBeenCalledWith({
        type: 'SET_MOST_RECENT_EXECUTION',
        // eslint-disable-next-line @typescript-eslint/no-unsafe-assignment -- vitest asymmetric matcher
        payload: expect.objectContaining({ executionId: 'exec-retry' }),
      })
    )
    expect(dispatch).not.toHaveBeenCalledWith(expect.objectContaining({ type: 'SET_WORKFLOW_NAME' }) as unknown)
  })

  describe('preserveWorkflow mode', () => {
    it('skips content replacement when preserveWorkflow is true', () => {
      const replaceSpy = vi.spyOn(useWorkflowStore.getState(), 'replaceWorkflowContent')
      const opts = buildOptions({ executionCopy: buildExecutionCopy({ preserveWorkflow: true }) })
      renderHook(() => useExecutionCopyToEditor(opts))
      expect(replaceSpy).not.toHaveBeenCalled()
    })

    it('does not overwrite workflow name when preserveWorkflow is true', () => {
      const dispatch = vi.fn()
      const opts = buildOptions({ dispatch, executionCopy: buildExecutionCopy({ preserveWorkflow: true }) })
      renderHook(() => useExecutionCopyToEditor(opts))
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
      renderHook(() => useExecutionCopyToEditor(opts))
      await waitFor(() =>
        expect(opts.dispatch).toHaveBeenCalledWith({
          type: 'SET_MOST_RECENT_EXECUTION',
          payload: {
            executionId: 'exec-fork',
            copiedRunActivityIds: ['existing-task', 'existing-trigger'],
          },
        })
      )
    })

    it('does not mark dirty or show toast when preserveWorkflow is true', () => {
      const opts = buildOptions({ executionCopy: buildExecutionCopy({ preserveWorkflow: true }) })
      renderHook(() => useExecutionCopyToEditor(opts))
      expect(opts.markDirty).not.toHaveBeenCalled()
      expect(opts.showSuccess).not.toHaveBeenCalled()
    })
  })
})
