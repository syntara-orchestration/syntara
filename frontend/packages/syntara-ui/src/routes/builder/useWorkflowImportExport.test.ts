import { renderHook, act, waitFor } from '@testing-library/react'
import { describe, expect, it, vi, beforeEach } from 'vitest'

import { useWorkflowImportExport } from './useWorkflowImportExport'

const mockShowError = vi.fn()
const mockDispatch = vi.fn()
const mockMarkDirty = vi.fn()
const mockOnPendingImport = vi.fn()
const mockDownload = vi.fn()
const mockParseWorkflowFile = vi.fn<(...args: unknown[]) => Record<string, unknown>>()
const mockValidateFileSize = vi.fn()
const mockLoadDefinition =
  vi.fn<() => { workflowDef: Record<string, unknown>; edges: unknown[]; nodePositions: Record<string, unknown> }>()
const mockBuildDefinition = vi.fn<(...args: unknown[]) => Record<string, unknown>>()
const mockReplaceWorkflowContent = vi.fn()
const mockGetState = vi.fn<() => Record<string, unknown>>()

const mockHandleVerify = vi.fn()

vi.mock('../../providers/alerts', () => ({
  useAlerts: () => ({ showError: mockShowError }),
}))

vi.mock('../../stores/useWorkflowStore', () => ({
  useWorkflowStore: {
    getState: () => mockGetState(),
  },
}))

vi.mock('../../utils/apiErrors', () => ({
  getErrorMessage: (err: unknown) => (err instanceof Error ? err.message : 'Unknown error'),
}))

vi.mock('../../utils/downloadWorkflowExport', () => ({
  downloadWorkflowDefinition: (...args: unknown[]) => mockDownload(...args) as void,
  parseWorkflowFile: (...args: unknown[]) => mockParseWorkflowFile(...args),
  validateFileSize: (...args: unknown[]) => mockValidateFileSize(...args) as void,
}))

vi.mock('./useWorkflowVerification', () => ({
  useWorkflowVerification: () => ({ handleVerify: mockHandleVerify, isVerifying: false, validationErrorCount: 0 }),
}))

vi.mock('./utils/parseImportedDefinition', () => ({
  parseImportedDefinition: () => mockLoadDefinition(),
}))

vi.mock('./utils/workflowDefinitionBuilder', () => ({
  buildWorkflowDefinition: (...args: unknown[]) => mockBuildDefinition(...args),
}))

beforeEach(() => {
  vi.clearAllMocks()
  mockGetState.mockReturnValue({
    currentWorkflow: null,
    edges: [],
    replaceWorkflowContent: mockReplaceWorkflowContent,
  })
})

describe('useWorkflowImportExport', () => {
  function renderImportExportHook(isNew = true, workflowName = 'Test', workflowDescription = 'desc') {
    return renderHook(() =>
      useWorkflowImportExport({
        dispatch: mockDispatch,
        markDirty: mockMarkDirty,
        isNew,
        workflowName,
        workflowDescription,
        onPendingImport: mockOnPendingImport,
      })
    )
  }

  describe('handleExport', () => {
    it('closes kebab when no current workflow', () => {
      const { result } = renderImportExportHook()

      act(() => result.current.handleExport())

      expect(mockDispatch).toHaveBeenCalledWith({ type: 'SET_KEBAB_OPEN', payload: false })
      expect(mockDownload).not.toHaveBeenCalled()
    })

    it('exports and closes kebab on success', () => {
      mockGetState.mockReturnValue({
        currentWorkflow: {
          name: 'Test',
          description: 'desc',
          workflow: { activities: [] },
          triggers: [],
        },
        edges: [],
      })
      mockBuildDefinition.mockReturnValue({ nodes: [], edges: [], triggers: [] })

      const { result } = renderImportExportHook()

      act(() => result.current.handleExport())

      expect(mockBuildDefinition).toHaveBeenCalled()
      expect(mockDownload).toHaveBeenCalled()
      expect(mockDispatch).toHaveBeenCalledWith({ type: 'SET_KEBAB_OPEN', payload: false })
    })

    it('uses workflowName from hook options instead of stale store name', () => {
      mockGetState.mockReturnValue({
        currentWorkflow: {
          name: 'Old Stale Name',
          description: 'old description',
          workflow: { activities: [] },
          triggers: [],
        },
        edges: [],
      })
      mockBuildDefinition.mockReturnValue({ nodes: [], edges: [], triggers: [] })

      const { result } = renderImportExportHook(false, 'Renamed Workflow', 'new description')

      act(() => result.current.handleExport())

      expect(mockBuildDefinition).toHaveBeenCalledWith(
        'Renamed Workflow',
        'new description',
        expect.anything(),
        expect.anything(),
        expect.anything()
      )
      expect(mockDownload).toHaveBeenCalledWith(expect.anything(), 'Renamed Workflow')
    })

    it('falls back to "workflow" when workflowName is empty', () => {
      mockGetState.mockReturnValue({
        currentWorkflow: {
          name: 'Store Name',
          workflow: { activities: [] },
          triggers: [],
        },
        edges: [],
      })
      mockBuildDefinition.mockReturnValue({ nodes: [], edges: [], triggers: [] })

      const { result } = renderImportExportHook(false, '', '')

      act(() => result.current.handleExport())

      expect(mockBuildDefinition).toHaveBeenCalledWith(
        'workflow',
        '',
        expect.anything(),
        expect.anything(),
        expect.anything()
      )
      expect(mockDownload).toHaveBeenCalledWith(expect.anything(), 'workflow')
    })

    it('shows error toast and closes kebab on failure', () => {
      mockGetState.mockReturnValue({
        currentWorkflow: {
          name: 'Test',
          workflow: { activities: [] },
          triggers: [],
        },
        edges: [],
      })
      mockBuildDefinition.mockImplementation(() => {
        throw new Error('Build failed')
      })

      const { result } = renderImportExportHook()

      act(() => result.current.handleExport())

      expect(mockShowError).toHaveBeenCalledWith({
        title: 'Failed to export workflow',
        description: 'Build failed',
      })
      expect(mockDispatch).toHaveBeenCalledWith({ type: 'SET_KEBAB_OPEN', payload: false })
    })
  })

  describe('handleImportFile', () => {
    function createFileChangeEvent(file: File | null) {
      return {
        target: {
          files: file ? [file] : [],
          value: 'some-path',
        },
      } as unknown as React.ChangeEvent<HTMLInputElement>
    }

    it('does nothing when no file selected', () => {
      const { result } = renderImportExportHook()

      act(() => result.current.handleImportFile(createFileChangeEvent(null)))

      expect(mockValidateFileSize).not.toHaveBeenCalled()
    })

    it('imports file and dispatches name/description', async () => {
      const definition = {
        name: 'Imported',
        description: 'A workflow',
        triggers: [],
        nodes: [],
        edges: [],
      }
      mockValidateFileSize.mockReturnValue(undefined)
      mockParseWorkflowFile.mockReturnValue(definition)
      mockLoadDefinition.mockReturnValue({ workflowDef: {}, edges: [], nodePositions: {} })
      mockGetState.mockReturnValue({ replaceWorkflowContent: mockReplaceWorkflowContent })

      const file = new File([JSON.stringify(definition)], 'test.json', { type: 'application/json' })
      const { result } = renderImportExportHook()

      act(() => result.current.handleImportFile(createFileChangeEvent(file)))

      await waitFor(() => {
        expect(mockDispatch).toHaveBeenCalledWith({ type: 'SET_WORKFLOW_NAME', payload: 'Imported' })
      })
      expect(mockDispatch).toHaveBeenCalledWith({ type: 'SET_WORKFLOW_DESCRIPTION', payload: 'A workflow' })
      expect(mockMarkDirty).toHaveBeenCalled()
    })

    it('truncates name over 255 characters with toast', async () => {
      const longName = 'x'.repeat(300)
      const definition = { name: longName, triggers: [], nodes: [], edges: [] }
      mockValidateFileSize.mockReturnValue(undefined)
      mockParseWorkflowFile.mockReturnValue(definition)
      mockLoadDefinition.mockReturnValue({ workflowDef: {}, edges: [], nodePositions: {} })
      mockGetState.mockReturnValue({ replaceWorkflowContent: mockReplaceWorkflowContent })

      const file = new File(['{}'], 'test.json')
      const { result } = renderImportExportHook()

      act(() => result.current.handleImportFile(createFileChangeEvent(file)))

      await waitFor(() => {
        expect(mockDispatch).toHaveBeenCalledWith({
          type: 'SET_WORKFLOW_NAME',
          payload: 'x'.repeat(255),
        })
      })
      expect(mockShowError).toHaveBeenCalledWith({
        title: 'Import note',
        description: 'Workflow name was truncated to 255 characters',
      })
    })

    it('shows error toast on import failure', async () => {
      mockValidateFileSize.mockImplementation(() => {
        throw new Error('File is too large')
      })

      const file = new File(['{}'], 'test.json')
      const { result } = renderImportExportHook()

      act(() => result.current.handleImportFile(createFileChangeEvent(file)))

      await waitFor(() => {
        expect(mockShowError).toHaveBeenCalledWith({
          title: 'Failed to import workflow',
          description: 'File is too large',
        })
      })
    })

    it('calls onPendingImport instead of applying directly when isNew is false', async () => {
      const definition = {
        name: 'Imported',
        description: 'A workflow',
        triggers: [],
        nodes: [],
        edges: [],
      }
      mockValidateFileSize.mockReturnValue(undefined)
      mockParseWorkflowFile.mockReturnValue(definition)
      mockLoadDefinition.mockReturnValue({ workflowDef: {}, edges: [], nodePositions: {} })
      mockGetState.mockReturnValue({ replaceWorkflowContent: mockReplaceWorkflowContent })

      const file = new File([JSON.stringify(definition)], 'test.json', { type: 'application/json' })
      const { result } = renderImportExportHook(false)

      act(() => result.current.handleImportFile(createFileChangeEvent(file)))

      await waitFor(() => {
        expect(mockOnPendingImport).toHaveBeenCalledWith(
          expect.objectContaining({
            name: 'Imported',
            description: 'A workflow',
          })
        )
      })
      expect(mockReplaceWorkflowContent).not.toHaveBeenCalled()
      expect(mockMarkDirty).not.toHaveBeenCalled()
    })

    it('applies directly when isNew is true', async () => {
      const definition = {
        name: 'Imported',
        description: 'A workflow',
        triggers: [],
        nodes: [],
        edges: [],
      }
      mockValidateFileSize.mockReturnValue(undefined)
      mockParseWorkflowFile.mockReturnValue(definition)
      mockLoadDefinition.mockReturnValue({ workflowDef: {}, edges: [], nodePositions: {} })
      mockGetState.mockReturnValue({ replaceWorkflowContent: mockReplaceWorkflowContent })

      const file = new File([JSON.stringify(definition)], 'test.json', { type: 'application/json' })
      const { result } = renderImportExportHook(true)

      act(() => result.current.handleImportFile(createFileChangeEvent(file)))

      await waitFor(() => {
        expect(mockReplaceWorkflowContent).toHaveBeenCalled()
      })
      expect(mockMarkDirty).toHaveBeenCalled()
      expect(mockOnPendingImport).not.toHaveBeenCalled()
    })
  })

  it('returns a ref for the file input', () => {
    const { result } = renderImportExportHook()

    expect(result.current.importFileRef).toBeDefined()
    expect(result.current.importFileRef.current).toBeNull()
  })

  it('delegates handleVerify and isVerifying from useWorkflowVerification', () => {
    const { result } = renderImportExportHook()

    expect(result.current.handleVerify).toBe(mockHandleVerify)
    expect(result.current.isVerifying).toBe(false)
  })
})
