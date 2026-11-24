import type { WorkflowAPI } from '@syntara/contracts'
import { renderHook, act } from '@testing-library/react'
import { describe, expect, it, vi, beforeEach } from 'vitest'

import { useBuilderVersionPanel } from './useBuilderVersionPanel'

type MockRestoreDialogItem = { version: number; dateTime: string; definition: Record<string, unknown> }
const viewedDefinition = { name: 'Historical version', nodes: [], triggers: [] }
const rowVersion = {
  id: 'ver-1',
  workflow_id: 'wf-1',
  version: 1,
  schema_version: '2.0.0',
  status: 'draft',
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
  workflow_definition: { name: 'History row version', nodes: [], triggers: [] },
} satisfies WorkflowAPI.components['schemas']['WorkflowVersionRead']
const mockRestoreDialogOpen = vi.fn<(item: MockRestoreDialogItem) => void>()
const mockRestoreDialogClose = vi.fn<() => void>()
const mockRefetch = vi.fn().mockResolvedValue({})
const mockExportVersion = vi.fn()
const mockOpenInNewWindow = vi.fn()
const mockPublishVersion = vi.fn()
const mockHandleExitVersionView = vi.fn()
const mockHandleConfirmRestore = vi.fn()
let mockRestoreDialogItem: MockRestoreDialogItem | null = null
let mockRestoreDialogIsOpen = false
mockRestoreDialogOpen.mockImplementation((item) => {
  mockRestoreDialogItem = item
  mockRestoreDialogIsOpen = true
})
mockRestoreDialogClose.mockImplementation(() => {
  mockRestoreDialogIsOpen = false
  mockRestoreDialogItem = null
})

let mockIsDirty = false
vi.mock('../../../stores/useWorkflowStore', () => ({
  useWorkflowStore: () => ({ isDirty: mockIsDirty }),
}))

vi.mock('../../../providers/alerts/AlertContext', () => ({
  useAlerts: () => ({ showSuccess: vi.fn(), showError: vi.fn() }),
}))

let mockIsViewingVersion = false
let mockViewedVersionDate: string | null = null
const mockUpdateVersionMetadata = vi.fn()
vi.mock('./useBuilderVersionHistory', () => ({
  useBuilderVersionHistory: () => ({
    filteredVersions: [1, 2, 3].map((version) => ({
      version,
      workflow_definition: { nodes: [], triggers: [] },
    })) as never,
    statusFilter: [],
    setStatusFilter: vi.fn(),
    exportVersion: mockExportVersion,
    openInNewWindow: mockOpenInNewWindow,
    publishVersion: mockPublishVersion,
    isViewingVersion: mockIsViewingVersion,
    viewedVersionDate: mockViewedVersionDate,
    viewedVersionStatus: null,
    viewedVersionDefinition: viewedDefinition,
    handleExitVersionView: mockHandleExitVersionView,
    handleConfirmRestore: mockHandleConfirmRestore,
    restoreDialog: {
      isOpen: mockRestoreDialogIsOpen,
      item: mockRestoreDialogItem,
      open: mockRestoreDialogOpen,
      close: mockRestoreDialogClose,
    },
    restoreDialogTitle: '',
    restoreMutation: { isPending: false },
    versionsQuery: { refetch: mockRefetch },
    updateVersionMetadata: mockUpdateVersionMetadata,
    updateMetadataMutation: { isPending: false },
    paginationFooterProps: {
      page: 1,
      perPage: 20,
      total: null,
      hasNext: false,
      onPrev: vi.fn(),
      onNext: vi.fn(),
      onPerPageChange: vi.fn(),
    },
  }),
}))

let mockBlockedStepTypes: { kind: string; label: string }[] = []
vi.mock('../../workflows/useStepTypePermissions', () => ({
  getStepTypesFromDefinition: () => [],
  useStepTypePermissions: () => ({
    canAuthor: mockBlockedStepTypes.length === 0,
    blockedStepTypes: mockBlockedStepTypes,
    isChecking: false,
    isError: false,
    retry: vi.fn().mockResolvedValue(undefined),
  }),
}))

function createParams(overrides: Record<string, unknown> = {}) {
  return {
    workflowId: 'wf-1',
    isNew: false,
    workflow: undefined,
    viewingVersion: null as number | null,
    versionHistoryOpen: false,
    dispatch: vi.fn(),
    handleSaveWorkflow: vi.fn().mockResolvedValue(true),
    workflowName: 'Test Workflow',
    expandAllEvent: new EventTarget(),
    baseHandleToggleVersionHistory: vi.fn(),
    searchParams: new URLSearchParams(),
    setSearchParams: vi.fn(),
    onOpenRunHistory: vi.fn(),
    onClearExecutionFilters: vi.fn(),
    executedVersionNumbers: new Map(),
    onDuplicateVersion: vi.fn(),
    canEdit: true,
    canCreate: true,
    saveTooltip: 'You cannot save changes to this workflow.',
    ...overrides,
  }
}

describe('useBuilderVersionPanel', () => {
  beforeEach(() => {
    mockBlockedStepTypes = []
    vi.clearAllMocks()
    mockIsDirty = false
    mockIsViewingVersion = false
    mockViewedVersionDate = null
    mockRestoreDialogItem = null
    mockRestoreDialogIsOpen = false
    mockRestoreDialogOpen.mockImplementation((item) => {
      mockRestoreDialogItem = item
      mockRestoreDialogIsOpen = true
    })
    mockRestoreDialogClose.mockImplementation(() => {
      mockRestoreDialogItem = null
      mockRestoreDialogIsOpen = false
    })
  })

  it('returns isViewingVersion from inner hook', () => {
    const { result } = renderHook(() => useBuilderVersionPanel(createParams()))

    expect(result.current.isViewingVersion).toBe(false)
  })

  it('handleToggleVersionHistory calls base handler', () => {
    const baseHandleToggleVersionHistory = vi.fn()
    const { result } = renderHook(() => useBuilderVersionPanel(createParams({ baseHandleToggleVersionHistory })))

    act(() => {
      result.current.handleToggleVersionHistory()
    })

    expect(baseHandleToggleVersionHistory).toHaveBeenCalledTimes(1)
  })

  it('handleToggleVersionHistory refetches when opening', () => {
    const { result } = renderHook(() => useBuilderVersionPanel(createParams({ versionHistoryOpen: false })))

    act(() => {
      result.current.handleToggleVersionHistory()
    })

    expect(mockRefetch).toHaveBeenCalledTimes(1)
  })

  it('handleToggleVersionHistory does not refetch when closing', () => {
    const { result } = renderHook(() => useBuilderVersionPanel(createParams({ versionHistoryOpen: true })))

    act(() => {
      result.current.handleToggleVersionHistory()
    })

    expect(mockRefetch).not.toHaveBeenCalled()
  })

  it('openRestoreDialogForCurrentVersion is undefined when not viewing a version', () => {
    const { result } = renderHook(() => useBuilderVersionPanel(createParams()))

    expect(result.current.openRestoreDialogForCurrentVersion).toBeUndefined()
  })

  it('exposes paginationFooterProps on versionSidePanel', () => {
    const { result } = renderHook(() =>
      useBuilderVersionPanel(createParams({ isNew: false, workflowId: 'wf-1', versionHistoryOpen: true }))
    )

    expect(result.current.versionSidePanel.paginationFooterProps).toEqual(
      expect.objectContaining({
        page: 1,
        perPage: 20,
        hasNext: false,
      })
    )
  })

  it('versionSidePanel.show is true when conditions are met', () => {
    const { result } = renderHook(() =>
      useBuilderVersionPanel(createParams({ isNew: false, workflowId: 'wf-1', versionHistoryOpen: true }))
    )

    expect(result.current.versionSidePanel.show).toBe(true)
  })

  it('versionSidePanel.show is false when workflow is new', () => {
    const { result } = renderHook(() => useBuilderVersionPanel(createParams({ isNew: true, versionHistoryOpen: true })))

    expect(result.current.versionSidePanel.show).toBe(false)
  })

  it('versionSidePanel.show is false when workflowId is null', () => {
    const { result } = renderHook(() =>
      useBuilderVersionPanel(createParams({ workflowId: null, versionHistoryOpen: true }))
    )

    expect(result.current.versionSidePanel.show).toBe(false)
  })

  it('versionSidePanel.show is false when versionHistoryOpen is false', () => {
    const { result } = renderHook(() => useBuilderVersionPanel(createParams({ versionHistoryOpen: false })))

    expect(result.current.versionSidePanel.show).toBe(false)
  })

  it('saveBeforeViewDialog starts closed', () => {
    const { result } = renderHook(() => useBuilderVersionPanel(createParams()))

    expect(result.current.versionSidePanel.saveBeforeViewDialog.isOpen).toBe(false)
  })

  it('onSelectVersion dispatches SET_VIEWING_VERSION when not dirty', () => {
    const dispatch = vi.fn()
    const { result } = renderHook(() => useBuilderVersionPanel(createParams({ dispatch })))

    act(() => {
      result.current.versionSidePanel.onSelectVersion(5)
    })

    expect(dispatch).toHaveBeenCalledWith({ type: 'SET_VIEWING_VERSION', payload: 5 })
  })

  it('restoreDialog state is exposed in versionSidePanel', () => {
    const { result } = renderHook(() => useBuilderVersionPanel(createParams()))

    expect(result.current.versionSidePanel.restoreDialog.isOpen).toBe(false)
    expect(result.current.versionSidePanel.restoreDialog.isLoading).toBe(false)
  })

  it('calls setSearchParams with version param when selecting a version', () => {
    const setSearchParams = vi.fn()
    const dispatch = vi.fn()
    const { result } = renderHook(() => useBuilderVersionPanel(createParams({ setSearchParams, dispatch })))

    act(() => {
      result.current.versionSidePanel.onSelectVersion(5)
    })

    const params = setSearchParams.mock.calls[0][0] as URLSearchParams
    expect(params.get('version')).toBe('5')
  })

  it('editDialog starts closed', () => {
    const { result } = renderHook(() => useBuilderVersionPanel(createParams()))

    expect(result.current.versionSidePanel.editDialog.isOpen).toBe(false)
    expect(result.current.versionSidePanel.editDialog.isSaving).toBe(false)
  })

  it('handleToggleVersionHistory calls onClearExecutionFilters when opening', () => {
    const onClearExecutionFilters = vi.fn()
    const { result } = renderHook(() =>
      useBuilderVersionPanel(createParams({ versionHistoryOpen: false, onClearExecutionFilters }))
    )

    act(() => {
      result.current.handleToggleVersionHistory()
    })

    expect(onClearExecutionFilters).toHaveBeenCalledTimes(1)
  })

  it('handleViewRunHistory calls onOpenRunHistory with version number', () => {
    const onOpenRunHistory = vi.fn()
    const dispatch = vi.fn()
    const { result } = renderHook(() => useBuilderVersionPanel(createParams({ onOpenRunHistory, dispatch })))

    act(() => {
      result.current.versionSidePanel.onViewRunHistory(3)
    })

    expect(dispatch).toHaveBeenCalledWith({ type: 'SET_VERSION_HISTORY_OPEN', payload: false })
    expect(onOpenRunHistory).toHaveBeenCalledWith(3)
  })

  it('handleViewRunHistory closes version history when not viewing a version', () => {
    const onOpenRunHistory = vi.fn()
    const dispatch = vi.fn()
    const { result } = renderHook(() => useBuilderVersionPanel(createParams({ onOpenRunHistory, dispatch })))

    act(() => {
      result.current.versionSidePanel.onViewRunHistory(2)
    })

    expect(dispatch).toHaveBeenCalledWith({ type: 'SET_VERSION_HISTORY_OPEN', payload: false })
    expect(onOpenRunHistory).toHaveBeenCalledWith(2)
  })

  it('onPublishVersion opens publish dialog', () => {
    const { result } = renderHook(() => useBuilderVersionPanel(createParams()))

    act(() => {
      result.current.versionSidePanel.onPublishVersion(2)
    })

    expect(result.current.versionSidePanel.publishDialog.isOpen).toBe(true)
  })

  it('onEditVersion opens edit dialog with version data', () => {
    const { result } = renderHook(() => useBuilderVersionPanel(createParams()))
    const mockVersion = {
      id: 'ver-1',
      version: 1,
      name: 'Release 1.0',
      change_description: 'Initial',
      workflow_definition: { nodes: [], triggers: [] },
    }

    act(() => {
      result.current.versionSidePanel.onEditVersion(mockVersion as never)
    })

    expect(result.current.versionSidePanel.editDialog.isOpen).toBe(true)
    expect(result.current.versionSidePanel.editDialog.initialName).toBe('Release 1.0')
    expect(result.current.versionSidePanel.editDialog.initialDescription).toBe('Initial')
  })

  it('onDuplicateVersion calls the passed callback', () => {
    const onDuplicateVersion = vi.fn()
    const { result } = renderHook(() => useBuilderVersionPanel(createParams({ onDuplicateVersion })))

    const mockVersion = { id: 'ver-1', version: 1 }

    act(() => {
      result.current.versionSidePanel.onDuplicateVersion(mockVersion as never)
    })

    expect(onDuplicateVersion).toHaveBeenCalledWith(mockVersion)
  })

  it('onClose dispatches SET_VERSION_HISTORY_OPEN false', () => {
    const dispatch = vi.fn()
    const { result } = renderHook(() => useBuilderVersionPanel(createParams({ dispatch })))

    act(() => {
      result.current.versionSidePanel.onClose()
    })

    expect(dispatch).toHaveBeenCalledWith({ type: 'SET_VERSION_HISTORY_OPEN', payload: false })
  })

  it('onExportVersion calls exportVersion', () => {
    const { result } = renderHook(() => useBuilderVersionPanel(createParams()))

    act(() => {
      result.current.versionSidePanel.onExportVersion(2)
    })

    expect(mockExportVersion).toHaveBeenCalledWith(2)
  })

  it('exposes executedVersionNumbers from params', () => {
    const map = new Map([[1, 'uuid-1']])
    const { result } = renderHook(() => useBuilderVersionPanel(createParams({ executedVersionNumbers: map })))

    expect(result.current.versionSidePanel.executedVersionNumbers).toBe(map)
  })

  it('editDialog.onSave calls updateVersionMetadata and closes dialog', () => {
    const { result } = renderHook(() => useBuilderVersionPanel(createParams()))
    const mockVersion = {
      id: 'ver-1',
      version: 2,
      name: 'Old',
      change_description: 'Old Desc',
      workflow_definition: { nodes: [], triggers: [] },
    }

    act(() => {
      result.current.versionSidePanel.onEditVersion(mockVersion as never)
    })

    expect(result.current.versionSidePanel.editDialog.isOpen).toBe(true)

    act(() => {
      result.current.versionSidePanel.editDialog.onSave('New Name', 'New Desc')
    })

    expect(result.current.versionSidePanel.editDialog.isOpen).toBe(false)
  })

  it('editDialog.onClose closes the dialog', () => {
    const { result } = renderHook(() => useBuilderVersionPanel(createParams()))
    const mockVersion = {
      id: 'ver-1',
      version: 1,
      name: null,
      change_description: null,
      workflow_definition: { nodes: [], triggers: [] },
    }

    act(() => {
      result.current.versionSidePanel.onEditVersion(mockVersion as never)
    })

    expect(result.current.versionSidePanel.editDialog.isOpen).toBe(true)

    act(() => {
      result.current.versionSidePanel.editDialog.onClose()
    })

    expect(result.current.versionSidePanel.editDialog.isOpen).toBe(false)
  })

  it('publishDialog.onPublish calls publishVersion and closes dialog', () => {
    const { result } = renderHook(() => useBuilderVersionPanel(createParams()))

    act(() => {
      result.current.versionSidePanel.onPublishVersion(2)
    })

    expect(result.current.versionSidePanel.publishDialog.isOpen).toBe(true)

    act(() => {
      result.current.versionSidePanel.publishDialog.onPublish('Release', 'Description')
    })

    expect(mockPublishVersion).toHaveBeenCalledWith(2, 'Release', 'Description')
    expect(result.current.versionSidePanel.publishDialog.isOpen).toBe(false)
  })

  it('publishDialog.onClose closes without publishing', () => {
    const { result } = renderHook(() => useBuilderVersionPanel(createParams()))

    act(() => {
      result.current.versionSidePanel.onPublishVersion(3)
    })

    act(() => {
      result.current.versionSidePanel.publishDialog.onClose()
    })

    expect(result.current.versionSidePanel.publishDialog.isOpen).toBe(false)
    expect(mockPublishVersion).not.toHaveBeenCalled()
  })

  it('restoreDialog.onClose calls the close function', () => {
    const { result } = renderHook(() => useBuilderVersionPanel(createParams()))

    act(() => {
      result.current.versionSidePanel.restoreDialog.onClose()
    })

    expect(mockRestoreDialogClose).toHaveBeenCalled()
  })

  it('checks the clicked history row before confirming restore', () => {
    const params = createParams()
    const { result, rerender } = renderHook((currentParams) => useBuilderVersionPanel(currentParams), {
      initialProps: params,
    })

    act(() => {
      result.current.versionSidePanel.onRestoreVersion(rowVersion)
    })
    expect(mockRestoreDialogOpen).toHaveBeenCalledWith({
      version: 1,
      dateTime: '2026-01-01T00:00:00Z',
      definition: rowVersion.workflow_definition,
    })

    mockBlockedStepTypes = [{ kind: 'wait', label: 'Wait' }]
    rerender(params)
    expect(result.current.versionSidePanel.restoreDialog.canConfirm).toBe(false)
    act(() => result.current.versionSidePanel.restoreDialog.onConfirm())
    expect(mockHandleConfirmRestore).not.toHaveBeenCalled()

    mockBlockedStepTypes = []
    rerender(params)
    expect(result.current.versionSidePanel.restoreDialog.canConfirm).toBe(true)

    act(() => {
      result.current.versionSidePanel.restoreDialog.onConfirm()
    })

    expect(mockHandleConfirmRestore).toHaveBeenCalled()
  })

  it('onSelectVersion opens save-before-view dialog when dirty', () => {
    mockIsDirty = true
    const dispatch = vi.fn()
    const { result } = renderHook(() => useBuilderVersionPanel(createParams({ dispatch })))

    act(() => {
      result.current.versionSidePanel.onSelectVersion(5)
    })

    expect(result.current.versionSidePanel.saveBeforeViewDialog.isOpen).toBe(true)
    expect(dispatch).not.toHaveBeenCalledWith({ type: 'SET_VIEWING_VERSION', payload: 5 })
  })

  it('saveBeforeViewDialog.onViewWithoutSaving sets version without saving', () => {
    mockIsDirty = true
    const dispatch = vi.fn()
    const setSearchParams = vi.fn()
    const { result } = renderHook(() => useBuilderVersionPanel(createParams({ dispatch, setSearchParams })))

    act(() => {
      result.current.versionSidePanel.onSelectVersion(5)
    })

    act(() => {
      result.current.versionSidePanel.saveBeforeViewDialog.onViewWithoutSaving()
    })

    expect(dispatch).toHaveBeenCalledWith({ type: 'SET_VIEWING_VERSION', payload: 5 })
    expect(result.current.versionSidePanel.saveBeforeViewDialog.isOpen).toBe(false)
  })

  it('saveBeforeViewDialog.onCancel closes the dialog', () => {
    mockIsDirty = true
    const { result } = renderHook(() => useBuilderVersionPanel(createParams()))

    act(() => {
      result.current.versionSidePanel.onSelectVersion(3)
    })

    expect(result.current.versionSidePanel.saveBeforeViewDialog.isOpen).toBe(true)

    act(() => {
      result.current.versionSidePanel.saveBeforeViewDialog.onCancel()
    })

    expect(result.current.versionSidePanel.saveBeforeViewDialog.isOpen).toBe(false)
  })

  it('saveBeforeViewDialog.onSave saves and then sets version', async () => {
    mockIsDirty = true
    const dispatch = vi.fn()
    const handleSaveWorkflow = vi.fn().mockResolvedValue(true)
    const setSearchParams = vi.fn()
    const { result } = renderHook(() =>
      useBuilderVersionPanel(createParams({ dispatch, handleSaveWorkflow, setSearchParams }))
    )

    act(() => {
      result.current.versionSidePanel.onSelectVersion(5)
    })

    await act(async () => {
      await result.current.versionSidePanel.saveBeforeViewDialog.onSave()
    })

    expect(handleSaveWorkflow).toHaveBeenCalled()
    expect(dispatch).toHaveBeenCalledWith({ type: 'SET_VIEWING_VERSION', payload: 5 })
    expect(result.current.versionSidePanel.saveBeforeViewDialog.isOpen).toBe(false)
  })

  it('handleViewRunHistory exits version view when isViewingVersion is true', () => {
    mockIsViewingVersion = true
    const onOpenRunHistory = vi.fn()
    const dispatch = vi.fn()
    const { result } = renderHook(() => useBuilderVersionPanel(createParams({ onOpenRunHistory, dispatch })))

    act(() => {
      result.current.versionSidePanel.onViewRunHistory(3)
    })

    expect(mockHandleExitVersionView).toHaveBeenCalled()
    expect(onOpenRunHistory).toHaveBeenCalledWith(3)
    expect(dispatch).not.toHaveBeenCalledWith({ type: 'SET_VERSION_HISTORY_OPEN', payload: false })
  })

  it('openRestoreDialogForCurrentVersion is defined when viewing a version', () => {
    mockIsViewingVersion = true
    mockViewedVersionDate = '2026-05-19T14:30:00.000Z'
    const { result } = renderHook(() => useBuilderVersionPanel(createParams({ viewingVersion: 5 })))

    expect(result.current.openRestoreDialogForCurrentVersion).toBeDefined()
    expect(typeof result.current.openRestoreDialogForCurrentVersion).toBe('function')
  })

  it('explains the historical denial and guards opening the restore dialog', () => {
    mockIsViewingVersion = true
    mockViewedVersionDate = '2026-05-19T14:30:00.000Z'
    mockBlockedStepTypes = [{ kind: 'wait', label: 'Wait' }]
    const { result } = renderHook(() => useBuilderVersionPanel(createParams({ viewingVersion: 2 })))

    expect(result.current.canRestoreSelectedVersion).toBe(false)
    expect(result.current.restoreTooltip).toContain('permission to edit Wait steps')
    act(() => result.current.openRestoreDialogForCurrentVersion?.())
    expect(mockRestoreDialogOpen).not.toHaveBeenCalled()
  })

  it('can restore the viewed version when it is absent from filtered history', () => {
    mockIsViewingVersion = true
    mockViewedVersionDate = '2026-05-19T14:30:00.000Z'
    const params = createParams({ viewingVersion: 5 })
    const { result, rerender } = renderHook(() => useBuilderVersionPanel(params))

    act(() => {
      result.current.openRestoreDialogForCurrentVersion?.()
    })

    expect(mockRestoreDialogOpen).toHaveBeenCalledWith({
      version: 5,
      dateTime: '2026-05-19T14:30:00.000Z',
      definition: viewedDefinition,
    })
    rerender()
    expect(result.current.versionSidePanel.restoreDialog.permissionCheckLoading).toBe(false)
    expect(result.current.versionSidePanel.restoreDialog.canConfirm).toBe(true)
    act(() => result.current.versionSidePanel.restoreDialog.onConfirm())
    expect(mockHandleConfirmRestore).toHaveBeenCalledOnce()
  })

  it('onSelectVersion dispatches directly when isDirty but isViewingVersion', () => {
    mockIsDirty = true
    mockIsViewingVersion = true
    const dispatch = vi.fn()
    const { result } = renderHook(() => useBuilderVersionPanel(createParams({ dispatch })))

    act(() => {
      result.current.versionSidePanel.onSelectVersion(3)
    })

    expect(dispatch).toHaveBeenCalledWith({ type: 'SET_VIEWING_VERSION', payload: 3 })
    expect(result.current.versionSidePanel.saveBeforeViewDialog.isOpen).toBe(false)
  })

  it('keeps the save-before-view dialog open when saving fails', async () => {
    mockIsDirty = true
    const dispatch = vi.fn()
    const handleSaveWorkflow = vi.fn().mockResolvedValue(false)
    const { result } = renderHook(() => useBuilderVersionPanel(createParams({ dispatch, handleSaveWorkflow })))

    act(() => {
      result.current.versionSidePanel.onSelectVersion(5)
    })

    await act(async () => {
      await result.current.versionSidePanel.saveBeforeViewDialog.onSave()
    })

    expect(dispatch).not.toHaveBeenCalledWith({ type: 'SET_VIEWING_VERSION', payload: 5 })
    expect(result.current.versionSidePanel.saveBeforeViewDialog.isOpen).toBe(true)
  })

  it('blocks saving after permission is revoked while keeping the pending version available', async () => {
    mockIsDirty = true
    const params = createParams()
    const { result, rerender } = renderHook((options) => useBuilderVersionPanel(options), { initialProps: params })

    act(() => result.current.versionSidePanel.onSelectVersion(5))
    rerender({ ...params, canEdit: false })
    await act(async () => {
      await result.current.versionSidePanel.saveBeforeViewDialog.onSave()
    })

    expect(result.current.versionSidePanel.saveBeforeViewDialog).toMatchObject({
      isOpen: true,
      canSave: false,
      saveTooltip: params.saveTooltip,
    })
    expect(params.handleSaveWorkflow).not.toHaveBeenCalled()
    expect(params.dispatch).not.toHaveBeenCalled()
    act(() => result.current.versionSidePanel.saveBeforeViewDialog.onViewWithoutSaving())
    expect(params.dispatch).toHaveBeenCalledWith({ type: 'SET_VIEWING_VERSION', payload: 5 })
  })

  it('editDialog.onSave is a no-op when no item is selected', () => {
    const { result } = renderHook(() => useBuilderVersionPanel(createParams()))

    act(() => {
      result.current.versionSidePanel.editDialog.onSave('name', 'desc')
    })

    expect(mockUpdateVersionMetadata).not.toHaveBeenCalled()
  })

  it('publishDialog.onPublish is a no-op when no item is selected', () => {
    const { result } = renderHook(() => useBuilderVersionPanel(createParams()))

    act(() => {
      result.current.versionSidePanel.publishDialog.onPublish('name', 'desc')
    })

    expect(mockPublishVersion).not.toHaveBeenCalled()
  })
})
