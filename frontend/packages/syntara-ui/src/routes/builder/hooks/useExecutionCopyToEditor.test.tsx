import { act, renderHook } from '@testing-library/react'
import { describe, expect, it, vi, beforeEach, type MockInstance } from 'vitest'

import type { NodeKind } from '../../../hooks/useNodeKindsQuery'
import { useWorkflowStore } from '../../../stores/useWorkflowStore'
import { STEP_TYPE_PERMISSIONS_UNAVAILABLE_TOOLTIP } from '../stepTypePaletteGating'

import type { ExecutionCopyData } from './useExecutionCopyToEditor'
import { useExecutionCopyToEditor } from './useExecutionCopyToEditor'

const { mockNodeKinds, mockUseNodeKindsQuery } = vi.hoisted(() => {
  const state = {
    byKind: new Map<string, unknown>(),
    isLoading: false,
    isUnavailable: false,
  }
  return {
    mockNodeKinds: state,
    mockUseNodeKindsQuery: vi.fn<
      (
        projectId: string | null | undefined,
        options?: { enabled?: boolean }
      ) => {
        nodeKindByKind: Map<string, unknown>
        isLoading: boolean
        isUnavailable: boolean
      }
    >(() => ({
      nodeKindByKind: state.byKind,
      isLoading: state.isLoading,
      isUnavailable: state.isUnavailable,
    })),
  }
})

vi.mock('../../../hooks/useNodeKindsQuery', () => ({ useNodeKindsQuery: mockUseNodeKindsQuery }))

vi.mock('../utils/parseImportedDefinition', () => ({
  parseImportedDefinition: vi.fn((def: Record<string, unknown>) => ({
    workflowDef: {
      name: def.name ?? 'parsed-wf',
      description: def.description ?? '',
      workflow: {
        activities: [
          { id: 'copied-task-1', type: 'http_request' },
          { id: 'copied-cond-1', type: 'script' },
        ],
      },
      triggers: [{ id: 'copied-trigger-1', type: 'manual_trigger' }],
    },
    edges: [
      { id: 'e1', source: 'copied-trigger-1', target: 'copied-task-1' },
      { id: 'e2', source: 'copied-task-1', target: 'copied-cond-1' },
    ],
    nodePositions: {
      'copied-task-1': { x: 0, y: 0 },
      'copied-cond-1': { x: 1, y: 1 },
      'copied-trigger-1': { x: 2, y: 2 },
    },
  })),
}))

function verdict(kind: string, label: string): NodeKind {
  return { kind, category: 'action', can_write: false, blocked_by: { kind, label } }
}

function buildOptions(overrides: Partial<Parameters<typeof useExecutionCopyToEditor>[0]> = {}) {
  return {
    executionCopy: undefined as ExecutionCopyData | undefined,
    projectId: 'proj-1' as string | undefined,
    dispatch: vi.fn(),
    markDirty: vi.fn(),
    showSuccess: vi.fn(),
    showError: vi.fn(),
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
  let replaceStateSpy: MockInstance<History['replaceState']>

  beforeEach(() => {
    vi.clearAllMocks()
    useWorkflowStore.getState().setWorkflow({
      schema_version: '2.0.0',
      name: 'existing',
      description: '',
      workflow: { activities: [] },
    })
    replaceStateSpy = vi.spyOn(window.history, 'replaceState').mockImplementation(() => {})
    mockNodeKinds.byKind = new Map()
    mockNodeKinds.isLoading = false
    mockNodeKinds.isUnavailable = false
  })

  it('does nothing when executionCopy is undefined', () => {
    const opts = buildOptions()
    renderHook(() => useExecutionCopyToEditor(opts))
    expect(mockUseNodeKindsQuery).toHaveBeenCalledWith('proj-1', { enabled: false })
    expect(opts.dispatch).not.toHaveBeenCalled()
    expect(opts.showSuccess).not.toHaveBeenCalled()
  })

  it('does nothing when currentWorkflow is null', () => {
    useWorkflowStore.getState().setWorkflow(null)
    const opts = buildOptions({ executionCopy: buildExecutionCopy() })
    renderHook(() => useExecutionCopyToEditor(opts))
    expect(opts.dispatch).not.toHaveBeenCalled()
  })

  it('calls replaceWorkflowContent with parsed definition', () => {
    const replaceSpy = vi.spyOn(useWorkflowStore.getState(), 'replaceWorkflowContent')
    const opts = buildOptions({ executionCopy: buildExecutionCopy() })
    renderHook(() => useExecutionCopyToEditor(opts))
    expect(replaceSpy).toHaveBeenCalledOnce()
  })

  it('dispatches SET_WORKFLOW_NAME from parsed definition', () => {
    const opts = buildOptions({ executionCopy: buildExecutionCopy() })
    renderHook(() => useExecutionCopyToEditor(opts))
    expect(opts.dispatch).toHaveBeenCalledWith(expect.objectContaining({ type: 'SET_WORKFLOW_NAME' }) as unknown)
  })

  it('dispatches SET_MOST_RECENT_EXECUTION with execution ID and copied activity allowlist', () => {
    const opts = buildOptions({ executionCopy: buildExecutionCopy({ executionId: 'exec-abc' }) })
    renderHook(() => useExecutionCopyToEditor(opts))
    expect(opts.dispatch).toHaveBeenCalledWith({
      type: 'SET_MOST_RECENT_EXECUTION',
      payload: {
        executionId: 'exec-abc',
        copiedRunActivityIds: ['copied-task-1', 'copied-cond-1', 'copied-trigger-1'],
      },
    })
  })

  it('calls markDirty', () => {
    const opts = buildOptions({ executionCopy: buildExecutionCopy() })
    renderHook(() => useExecutionCopyToEditor(opts))
    expect(opts.markDirty).toHaveBeenCalledOnce()
  })

  it('shows success toast', () => {
    const opts = buildOptions({ executionCopy: buildExecutionCopy() })
    renderHook(() => useExecutionCopyToEditor(opts))
    expect(opts.showSuccess).toHaveBeenCalledWith({
      title: 'Run copied to editor',
      description: 'The run has been loaded into the editor with pinned runtime data.',
    })
  })

  it('cleans the URL query params', () => {
    const opts = buildOptions({ executionCopy: buildExecutionCopy() })
    renderHook(() => useExecutionCopyToEditor(opts))
    expect(replaceStateSpy).toHaveBeenCalledWith({}, '', window.location.pathname)
  })

  it('applies only once even on re-render', () => {
    const opts = buildOptions({ executionCopy: buildExecutionCopy() })
    const { rerender } = renderHook(() => useExecutionCopyToEditor(opts))
    rerender()
    rerender()
    expect(opts.showSuccess).toHaveBeenCalledOnce()
  })

  describe('step types the user may not write', () => {
    beforeEach(() => {
      mockNodeKinds.byKind = new Map([
        ['script', verdict('script', 'Script')],
        ['manual_trigger', verdict('manual_trigger', 'Manual trigger')],
      ])
    })

    it('copies as before when every step type is permitted', () => {
      mockNodeKinds.byKind = new Map(
        ['http_request', 'script', 'manual_trigger'].map((kind) => [
          kind,
          { kind, category: 'action', can_write: true, blocked_by: null },
        ])
      )
      const replaceSpy = vi.spyOn(useWorkflowStore.getState(), 'replaceWorkflowContent')
      const opts = buildOptions({ executionCopy: buildExecutionCopy() })
      const { result } = renderHook(() => useExecutionCopyToEditor(opts))

      expect(result.current.blockedRunCopy).toBeNull()
      expect(replaceSpy).toHaveBeenCalledOnce()
      expect(opts.dispatch).toHaveBeenCalledWith(
        expect.objectContaining({ type: 'SET_MOST_RECENT_EXECUTION' }) as unknown
      )
    })

    it('opens the prompt with the blocked step type labels and copies nothing yet', () => {
      const replaceSpy = vi.spyOn(useWorkflowStore.getState(), 'replaceWorkflowContent')
      const opts = buildOptions({ executionCopy: buildExecutionCopy() })
      const { result } = renderHook(() => useExecutionCopyToEditor(opts))

      expect(result.current.blockedRunCopy).toEqual({ labels: ['Script', 'Manual trigger'] })
      expect(replaceSpy).not.toHaveBeenCalled()
      expect(opts.dispatch).not.toHaveBeenCalled()
      expect(opts.showSuccess).not.toHaveBeenCalled()
      expect(replaceStateSpy).not.toHaveBeenCalled()
    })

    it('copies the run without the blocked steps on confirm', () => {
      const replaceSpy = vi.spyOn(useWorkflowStore.getState(), 'replaceWorkflowContent')
      const opts = buildOptions({ executionCopy: buildExecutionCopy({ executionId: 'exec-abc' }) })
      const { result } = renderHook(() => useExecutionCopyToEditor(opts))

      act(() => result.current.confirmBlockedRunCopy())

      expect(replaceSpy).toHaveBeenCalledOnce()
      const [workflowDef, edges, nodePositions] = replaceSpy.mock.calls[0]
      expect(workflowDef.workflow.activities.map((a) => a.id)).toEqual(['copied-task-1'])
      expect(workflowDef.triggers).toEqual([])
      expect(edges).toEqual([])
      expect(nodePositions).toEqual({ 'copied-task-1': { x: 0, y: 0 } })
      expect(opts.dispatch).toHaveBeenCalledWith({
        type: 'SET_MOST_RECENT_EXECUTION',
        payload: { executionId: 'exec-abc', copiedRunActivityIds: ['copied-task-1'] },
      })
      expect(opts.dispatch).toHaveBeenCalledWith(expect.objectContaining({ type: 'SET_WORKFLOW_NAME' }) as unknown)
      expect(opts.markDirty).toHaveBeenCalledOnce()
      expect(opts.showSuccess).toHaveBeenCalledWith({
        title: 'Run copied to editor',
        description:
          'The run has been loaded into the editor with pinned runtime data. Steps of these types were left out: Script, Manual trigger.',
      })
      expect(replaceStateSpy).toHaveBeenCalledWith({}, '', window.location.pathname)
      expect(result.current.blockedRunCopy).toBeNull()
    })

    it('copies nothing on cancel, cleans the URL and does not prompt again', () => {
      const replaceSpy = vi.spyOn(useWorkflowStore.getState(), 'replaceWorkflowContent')
      const opts = buildOptions({ executionCopy: buildExecutionCopy() })
      const { result, rerender } = renderHook(() => useExecutionCopyToEditor(opts))

      act(() => result.current.cancelBlockedRunCopy())
      rerender()
      rerender()

      expect(result.current.blockedRunCopy).toBeNull()
      expect(replaceSpy).not.toHaveBeenCalled()
      expect(opts.dispatch).not.toHaveBeenCalled()
      expect(opts.showSuccess).not.toHaveBeenCalled()
      expect(replaceStateSpy).toHaveBeenCalledOnce()
      expect(replaceStateSpy).toHaveBeenCalledWith({}, '', window.location.pathname)
    })

    it('ignores a confirm after cancel', () => {
      const replaceSpy = vi.spyOn(useWorkflowStore.getState(), 'replaceWorkflowContent')
      const opts = buildOptions({ executionCopy: buildExecutionCopy() })
      const { result } = renderHook(() => useExecutionCopyToEditor(opts))

      act(() => result.current.cancelBlockedRunCopy())
      act(() => result.current.confirmBlockedRunCopy())

      expect(replaceSpy).not.toHaveBeenCalled()
    })
  })

  describe('verdict states', () => {
    it('waits while the verdicts load, then copies once they arrive', () => {
      mockNodeKinds.isLoading = true
      const replaceSpy = vi.spyOn(useWorkflowStore.getState(), 'replaceWorkflowContent')
      const opts = buildOptions({ executionCopy: buildExecutionCopy() })
      const { result, rerender } = renderHook(() => useExecutionCopyToEditor(opts))

      expect(replaceSpy).not.toHaveBeenCalled()
      expect(opts.dispatch).not.toHaveBeenCalled()
      expect(result.current.blockedRunCopy).toBeNull()

      mockNodeKinds.isLoading = false
      rerender()

      expect(replaceSpy).toHaveBeenCalledOnce()
      expect(opts.showSuccess).toHaveBeenCalledOnce()
    })

    it('waits while there is no project', () => {
      const replaceSpy = vi.spyOn(useWorkflowStore.getState(), 'replaceWorkflowContent')
      const opts = buildOptions({ executionCopy: buildExecutionCopy() })
      const { rerender } = renderHook(
        ({ projectId }: { projectId: string | undefined }) => useExecutionCopyToEditor({ ...opts, projectId }),
        { initialProps: { projectId: undefined as string | undefined } }
      )

      expect(replaceSpy).not.toHaveBeenCalled()
      expect(replaceStateSpy).not.toHaveBeenCalled()

      rerender({ projectId: 'proj-1' })

      expect(replaceSpy).toHaveBeenCalledOnce()
    })

    it('fails closed when the verdicts are unavailable', () => {
      mockNodeKinds.isUnavailable = true
      const replaceSpy = vi.spyOn(useWorkflowStore.getState(), 'replaceWorkflowContent')
      const opts = buildOptions({ executionCopy: buildExecutionCopy() })
      const { result, rerender } = renderHook(() => useExecutionCopyToEditor(opts))
      rerender()

      expect(opts.showError).toHaveBeenCalledOnce()
      expect(opts.showError).toHaveBeenCalledWith({
        title: 'Cannot copy run to editor',
        description: STEP_TYPE_PERMISSIONS_UNAVAILABLE_TOOLTIP,
      })
      expect(replaceSpy).not.toHaveBeenCalled()
      expect(opts.dispatch).not.toHaveBeenCalled()
      expect(result.current.blockedRunCopy).toBeNull()
      expect(replaceStateSpy).toHaveBeenCalledWith({}, '', window.location.pathname)
    })

    it('does not prompt when verdicts change after the copy', () => {
      const opts = buildOptions({ executionCopy: buildExecutionCopy() })
      const { result, rerender } = renderHook(() => useExecutionCopyToEditor(opts))
      expect(opts.showSuccess).toHaveBeenCalledOnce()

      mockNodeKinds.byKind = new Map([['script', verdict('script', 'Script')]])
      rerender()

      expect(result.current.blockedRunCopy).toBeNull()
    })
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

    it('still dispatches SET_MOST_RECENT_EXECUTION when preserveWorkflow is true', () => {
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
      expect(opts.dispatch).toHaveBeenCalledWith({
        type: 'SET_MOST_RECENT_EXECUTION',
        payload: {
          executionId: 'exec-fork',
          copiedRunActivityIds: ['existing-task', 'existing-trigger'],
        },
      })
    })

    it('does not wait on step-type verdicts when preserveWorkflow is true', () => {
      mockNodeKinds.isLoading = true
      const opts = buildOptions({
        projectId: undefined,
        executionCopy: buildExecutionCopy({ executionId: 'exec-fork', preserveWorkflow: true }),
      })
      const { result } = renderHook(() => useExecutionCopyToEditor(opts))

      expect(mockUseNodeKindsQuery).toHaveBeenCalledWith(undefined, { enabled: false })
      expect(opts.dispatch).toHaveBeenCalledWith(
        expect.objectContaining({ type: 'SET_MOST_RECENT_EXECUTION' }) as unknown
      )
      expect(result.current.blockedRunCopy).toBeNull()
    })

    it('does not mark dirty or show toast when preserveWorkflow is true', () => {
      const opts = buildOptions({ executionCopy: buildExecutionCopy({ preserveWorkflow: true }) })
      renderHook(() => useExecutionCopyToEditor(opts))
      expect(opts.markDirty).not.toHaveBeenCalled()
      expect(opts.showSuccess).not.toHaveBeenCalled()
    })
  })
})
