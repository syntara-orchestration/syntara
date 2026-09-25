import { act, renderHook } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { WorkflowDefinition } from '../../../stores/workflowStoreTypes'
import type { ConflictAction, ConflictInfo } from '../VersionConflictDialog'

import { useBuilderConflict, type ConflictActions } from './useBuilderConflict'

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

const mockWorkflowFetchClientPOST = vi.fn()
const mockExecutionsFetchClientPOST = vi.fn()

vi.mock('../../../client', () => ({
  workflowFetchClient: {
    POST: (...args: unknown[]): unknown => mockWorkflowFetchClientPOST(...args),
  },
  executionsFetchClient: {
    POST: (...args: unknown[]): unknown => mockExecutionsFetchClientPOST(...args),
  },
  authMiddleware: { onRequest: vi.fn() },
  interfaceTagMiddleware: { onRequest: vi.fn() },
}))

const mockGetState = vi.fn()

vi.mock('../../../stores/useWorkflowStore', () => ({
  useWorkflowStore: {
    getState: (...args: unknown[]): unknown => mockGetState(...args),
  },
}))

const mockBuildWorkflowDefinition = vi.fn()

vi.mock('../utils/workflowDefinitionBuilder', () => ({
  buildWorkflowDefinition: (...args: unknown[]): unknown => mockBuildWorkflowDefinition(...args),
}))

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function createDefaultParams(overrides?: Partial<Parameters<typeof useBuilderConflict>[0]>) {
  return {
    workflowId: 'wf-1',
    workflowName: 'Test Workflow',
    workflowDescription: 'Description',
    workflowProjectId: 'proj-1',
    selectedProjectId: 'proj-1',
    currentWorkflow: {
      workflow: { activities: [] },
      triggers: [],
      name: 'Test',
      description: 'desc',
    } as unknown as WorkflowDefinition,
    currentVersion: 3,
    isNew: false,
    setLocation: vi.fn(),
    showError: vi.fn(),
    markClean: vi.fn(),
    ...overrides,
  }
}

const conflictInfo: ConflictInfo = {
  currentVersion: 5,
  currentVersionName: null,
  expectedVersion: 3,
  expectedVersionName: null,
  expectedVersionCreatedAt: null,
  createdByUsername: 'other',
  createdAt: '2026-01-01',
}

function createMockActions(overrides?: Partial<ConflictActions>): ConflictActions {
  return {
    handleSaveWorkflow: vi.fn().mockResolvedValue(true),
    onPublish: vi.fn(),
    handleRunWorkflow: vi.fn().mockResolvedValue(undefined),
    ...overrides,
  }
}

/** Open the conflict dialog so handlers can be tested. */
function openConflict(
  result: { current: ReturnType<typeof useBuilderConflict> },
  action: ConflictAction = 'save',
  info: ConflictInfo = conflictInfo
) {
  act(() => {
    result.current.handleConflict(action)(info)
  })
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('useBuilderConflict', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockGetState.mockReturnValue({
      edges: [],
      nodePositions: {},
      _positionsUserModified: false,
    })
    mockBuildWorkflowDefinition.mockReturnValue({ built: true })
    mockWorkflowFetchClientPOST.mockResolvedValue({
      data: { id: 'new-id', current_version: 1 },
      error: undefined,
    })
    mockExecutionsFetchClientPOST.mockResolvedValue({
      data: { id: 'exec-1' },
      error: undefined,
    })
  })

  // ---- 1. Version initialization -----------------------------------------

  describe('version initialization', () => {
    it('sets loadedVersion from currentVersion when not a new workflow', () => {
      const params = createDefaultParams({ currentVersion: 7 })
      const { result } = renderHook(() => useBuilderConflict(params))

      expect(result.current.loadedVersion).toBe(7)
    })

    it('keeps loadedVersion null for new workflows', () => {
      const params = createDefaultParams({ isNew: true, currentVersion: 1 })
      const { result } = renderHook(() => useBuilderConflict(params))

      expect(result.current.loadedVersion).toBeNull()
    })

    it('keeps loadedVersion null when currentVersion is undefined', () => {
      const params = createDefaultParams({ currentVersion: undefined })
      const { result } = renderHook(() => useBuilderConflict(params))

      expect(result.current.loadedVersion).toBeNull()
    })
  })

  // ---- 2. handleConflict --------------------------------------------------

  describe('handleConflict', () => {
    it('opens the dialog with the correct action and info', () => {
      const params = createDefaultParams()
      const { result } = renderHook(() => useBuilderConflict(params))

      openConflict(result, 'publish', conflictInfo)

      expect(result.current.conflictDialogProps.isOpen).toBe(true)
      expect(result.current.conflictDialogProps.conflictAction).toBe('publish')
      expect(result.current.conflictDialogProps.conflictInfo).toEqual(conflictInfo)
    })
  })

  // ---- 3. onVersionUpdated ------------------------------------------------

  describe('onVersionUpdated', () => {
    it('updates loadedVersion', () => {
      const params = createDefaultParams()
      const { result } = renderHook(() => useBuilderConflict(params))

      act(() => {
        result.current.onVersionUpdated(10)
      })

      expect(result.current.loadedVersion).toBe(10)
    })
  })

  // ---- 4. setActions -------------------------------------------------------

  describe('setActions', () => {
    it('wires the actions ref so handlers can use them', async () => {
      const params = createDefaultParams()
      const { result } = renderHook(() => useBuilderConflict(params))
      const actions = createMockActions()

      act(() => {
        result.current.setActions(actions)
      })

      openConflict(result, 'save')

      await act(async () => {
        await result.current.conflictDialogProps.onSaveAsNewest('save')
      })

      expect(actions.handleSaveWorkflow).toHaveBeenCalledOnce()
    })
  })

  // ---- 5–9. handleSaveAsNewest -------------------------------------------

  describe('handleSaveAsNewest', () => {
    it('calls handleSaveWorkflow with expectedVersionOverride and closes dialog (save)', async () => {
      const params = createDefaultParams()
      const { result } = renderHook(() => useBuilderConflict(params))
      const actions = createMockActions()

      act(() => {
        result.current.setActions(actions)
      })
      openConflict(result, 'save')

      await act(async () => {
        await result.current.conflictDialogProps.onSaveAsNewest('save')
      })

      expect(actions.handleSaveWorkflow).toHaveBeenCalledWith({ expectedVersionOverride: 5 })
      expect(result.current.conflictDialogProps.isOpen).toBe(false)
    })

    it('saves then calls onPublish with version override (publish)', async () => {
      const params = createDefaultParams()
      const { result } = renderHook(() => useBuilderConflict(params))

      // Simulate save returning true and updating the version ref via onVersionUpdated
      const actions = createMockActions({
        handleSaveWorkflow: vi.fn().mockResolvedValue(true),
        onPublish: vi.fn(),
      })

      act(() => {
        result.current.setActions(actions)
        result.current.onVersionUpdated(8) // simulate saved version
      })
      openConflict(result, 'publish')

      await act(async () => {
        await result.current.conflictDialogProps.onSaveAsNewest('publish')
      })

      expect(actions.handleSaveWorkflow).toHaveBeenCalledWith({ expectedVersionOverride: 5 })
      expect(actions.onPublish).toHaveBeenCalledWith(undefined, undefined, expect.any(Function), {
        expectedVersionOverride: 8,
        versionOverride: 8,
      })
    })

    it('saves then calls handleRunWorkflow with skipPreflightCheck (run)', async () => {
      const params = createDefaultParams()
      const { result } = renderHook(() => useBuilderConflict(params))
      const actions = createMockActions()

      act(() => {
        result.current.setActions(actions)
      })
      openConflict(result, 'run')

      await act(async () => {
        await result.current.conflictDialogProps.onSaveAsNewest('run')
      })

      expect(actions.handleSaveWorkflow).toHaveBeenCalledOnce()
      expect(actions.handleRunWorkflow).toHaveBeenCalledWith(undefined, undefined, {
        skipPreflightCheck: true,
      })
      expect(result.current.conflictDialogProps.isOpen).toBe(false)
    })

    it('closes dialog without calling publish/run when save fails', async () => {
      const params = createDefaultParams()
      const { result } = renderHook(() => useBuilderConflict(params))
      const actions = createMockActions({
        handleSaveWorkflow: vi.fn().mockResolvedValue(false),
      })

      act(() => {
        result.current.setActions(actions)
      })
      openConflict(result, 'publish')

      await act(async () => {
        await result.current.conflictDialogProps.onSaveAsNewest('publish')
      })

      expect(actions.onPublish).not.toHaveBeenCalled()
      expect(result.current.conflictDialogProps.isOpen).toBe(false)
    })

    it('returns early without crashing when no actions are set', async () => {
      const params = createDefaultParams()
      const { result } = renderHook(() => useBuilderConflict(params))

      openConflict(result, 'save')

      // Should not throw
      await act(async () => {
        await result.current.conflictDialogProps.onSaveAsNewest('save')
      })

      // Dialog remains open since the handler returned early
      expect(result.current.conflictDialogProps.isOpen).toBe(true)
    })
  })

  // ---- 10–13. handleDuplicateWorkflow ------------------------------------

  describe('handleDuplicateWorkflow', () => {
    it('creates workflow via POST and navigates to builder (save)', async () => {
      const params = createDefaultParams()
      const { result } = renderHook(() => useBuilderConflict(params))

      openConflict(result, 'save')

      await act(async () => {
        await result.current.conflictDialogProps.onDuplicate('save')
      })

      expect(mockWorkflowFetchClientPOST).toHaveBeenCalledOnce()
      const [path, options] = mockWorkflowFetchClientPOST.mock.calls[0] as [string, { body: Record<string, unknown> }]
      expect(path).toBe('/workflows')
      expect(options.body).toMatchObject({
        name: 'Test Workflow (Copy)',
        description: 'Description',
        project_id: 'proj-1',
      })
      expect(params.setLocation).toHaveBeenCalledWith('/workflow-builder/new-id')
      expect(result.current.conflictDialogProps.isOpen).toBe(false)
    })

    it('creates workflow, runs it, and navigates to execution (run)', async () => {
      const params = createDefaultParams()
      const { result } = renderHook(() => useBuilderConflict(params))

      openConflict(result, 'run')

      await act(async () => {
        await result.current.conflictDialogProps.onDuplicate('run')
      })

      expect(mockExecutionsFetchClientPOST).toHaveBeenCalledWith('/executions', {
        body: { workflow_id: 'new-id', input_data: {}, trigger_node_id: '' },
      })
      expect(params.setLocation).toHaveBeenCalledWith('/executions/exec-1?history=closed')
    })

    it('creates workflow, publishes it, and navigates to builder (publish)', async () => {
      const params = createDefaultParams()
      const { result } = renderHook(() => useBuilderConflict(params))

      openConflict(result, 'publish')

      await act(async () => {
        await result.current.conflictDialogProps.onDuplicate('publish')
      })

      expect(mockWorkflowFetchClientPOST).toHaveBeenCalledWith(
        '/workflows/{workflow_id}/versions/{version}/publish',
        expect.objectContaining({
          params: { path: { workflow_id: 'new-id', version: 1 } },
          body: { name: null, change_description: null },
        })
      )
      expect(params.setLocation).toHaveBeenCalledWith('/workflow-builder/new-id')
    })

    it('shows error and does not navigate when create fails', async () => {
      mockWorkflowFetchClientPOST.mockResolvedValue({
        data: undefined,
        error: { message: 'Server error' },
      })

      const params = createDefaultParams()
      const { result } = renderHook(() => useBuilderConflict(params))

      openConflict(result, 'save')

      await act(async () => {
        await result.current.conflictDialogProps.onDuplicate('save')
      })

      expect(params.showError).toHaveBeenCalledWith({
        title: 'Duplicate failed',
        description: 'Failed to create duplicate workflow',
      })
      expect(params.setLocation).not.toHaveBeenCalled()
    })

    it('navigates to builder when run execution fails', async () => {
      mockExecutionsFetchClientPOST.mockResolvedValue({
        data: undefined,
        error: { message: 'Run error' },
      })

      const params = createDefaultParams()
      const { result } = renderHook(() => useBuilderConflict(params))

      openConflict(result, 'run')

      await act(async () => {
        await result.current.conflictDialogProps.onDuplicate('run')
      })

      expect(params.showError).toHaveBeenCalledWith({
        title: 'Run failed',
        description: 'Workflow duplicated but failed to run',
      })
      expect(params.setLocation).toHaveBeenCalledWith('/workflow-builder/new-id')
    })
  })

  // ---- 14. handleRefreshToLatest ------------------------------------------

  describe('handleRefreshToLatest', () => {
    it('closes dialog, calls markClean, and reloads the page', () => {
      const reloadMock = vi.fn()
      const originalLocation = window.location
      Object.defineProperty(window, 'location', {
        value: { ...originalLocation, reload: reloadMock },
        writable: true,
      })

      const params = createDefaultParams()
      const { result } = renderHook(() => useBuilderConflict(params))

      openConflict(result, 'save')

      act(() => {
        result.current.conflictDialogProps.onRefreshToLatest()
      })

      expect(result.current.conflictDialogProps.isOpen).toBe(false)
      expect(params.markClean).toHaveBeenCalledOnce()
      expect(reloadMock).toHaveBeenCalledOnce()
    })
  })

  // ---- 15. conflictDialogProps shape --------------------------------------

  describe('conflictDialogProps', () => {
    it('has correct initial values', () => {
      const params = createDefaultParams()
      const { result } = renderHook(() => useBuilderConflict(params))
      const props = result.current.conflictDialogProps

      expect(props.isOpen).toBe(false)
      expect(props.conflictAction).toBe('save')
      expect(props.conflictInfo).toBeUndefined()
      expect(props.isLoading).toBe(false)
      expect(typeof props.onClose).toBe('function')
      expect(typeof props.onSaveAsNewest).toBe('function')
      expect(typeof props.onDuplicate).toBe('function')
      expect(typeof props.onRefreshToLatest).toBe('function')
    })

    it('reflects correct values when dialog is open', () => {
      const params = createDefaultParams()
      const { result } = renderHook(() => useBuilderConflict(params))

      openConflict(result, 'run', conflictInfo)

      const props = result.current.conflictDialogProps
      expect(props.isOpen).toBe(true)
      expect(props.conflictAction).toBe('run')
      expect(props.conflictInfo).toEqual(conflictInfo)
    })

    it('onClose closes the dialog', () => {
      const params = createDefaultParams()
      const { result } = renderHook(() => useBuilderConflict(params))

      openConflict(result, 'save')
      expect(result.current.conflictDialogProps.isOpen).toBe(true)

      act(() => {
        result.current.conflictDialogProps.onClose()
      })

      expect(result.current.conflictDialogProps.isOpen).toBe(false)
    })
  })
})
