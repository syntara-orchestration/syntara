import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { BuilderEditorToolbar } from './BuilderEditorToolbar'

const mockHandleVerify = vi.fn()
const mockHandleExport = vi.fn()
const mockHandleImportFile = vi.fn()
let mockIsVerifying = false
let mockValidationErrorCount = 0

vi.mock('../../stores/useWorkflowStore', () => ({
  useWorkflowStore: (selector: (state: Record<string, unknown>) => unknown) =>
    selector({
      currentWorkflow: {
        workflow: {
          activities: [{ id: 'n1', type: 'script', name: 'Step', parameters: {} }],
        },
      },
    }),
}))

vi.mock('./useWorkflowImportExport', () => ({
  useWorkflowImportExport: () => ({
    importFileRef: { current: null },
    handleImportFile: mockHandleImportFile,
    handleExport: mockHandleExport,
    handleVerify: mockHandleVerify,
    isVerifying: mockIsVerifying,
    validationErrorCount: mockValidationErrorCount,
  }),
}))

describe('BuilderEditorToolbar', () => {
  const defaultProps = {
    isBuiltin: false,
    isNew: false,
    workflow: { id: 'wf-1' },
    isPending: false,
    isDirty: true,
    lastSavedAt: '2026-01-15T14:30:00Z',
    isKebabOpen: false,
    publishedVersionId: null as string | null,
    currentVersion: 1 as number | undefined,
    isAddNodePanelOpen: false,
    hasNoWorkflowNodes: false,
    workflowName: 'Test Workflow',
    workflowDescription: 'A test workflow',
    dispatch: vi.fn(),
    markDirty: vi.fn(),
    handleToggleHistory: vi.fn(),
    handleToggleVersionHistory: vi.fn(),
    handleToggleDetails: vi.fn(),
    handleSaveWorkflow: vi.fn().mockResolvedValue(true),
    onPublishClick: vi.fn(),
    onUnpublish: vi.fn(),
    onDuplicate: vi.fn(),
    onPendingImport: vi.fn(),
    builderPermissions: {
      canEdit: true,
      canCreate: true,
      canRun: true,
      canDelete: true,
      isLoading: false,
      tooltips: { edit: '', save: '', publish: '', unpublish: '', run: '', delete: '', create: '' },
    },
  }

  beforeEach(() => {
    mockHandleVerify.mockImplementation((onValid?: () => void) => onValid?.())
    mockIsVerifying = false
    mockValidationErrorCount = 0
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it('renders Add Step button', () => {
    render(<BuilderEditorToolbar {...defaultProps} />)

    expect(screen.getByRole('button', { name: /Add Step/i })).toBeInTheDocument()
  })

  it('shows active state when Add step panel is open', () => {
    render(<BuilderEditorToolbar {...defaultProps} isAddNodePanelOpen />)

    expect(screen.getByRole('button', { name: /Add Step/i })).toHaveAttribute('aria-pressed', 'true')
  })

  it('shows inactive state when Add step panel is closed', () => {
    render(<BuilderEditorToolbar {...defaultProps} isAddNodePanelOpen={false} />)

    expect(screen.getByRole('button', { name: /Add Step/i })).toHaveAttribute('aria-pressed', 'false')
  })

  it('hides Add Step button when workflow has no triggers or steps yet', () => {
    render(<BuilderEditorToolbar {...defaultProps} isNew hasNoWorkflowNodes isAddNodePanelOpen workflow={undefined} />)

    expect(screen.queryByRole('button', { name: /Add Step/i })).not.toBeInTheDocument()
    expect(screen.getAllByRole('separator')).toHaveLength(2)
  })

  it('opens add node panel when Add Step is clicked', async () => {
    const user = userEvent.setup()
    const dispatch = vi.fn()

    render(<BuilderEditorToolbar {...defaultProps} dispatch={dispatch} />)

    await user.click(screen.getByRole('button', { name: /Add Step/i }))

    expect(dispatch).toHaveBeenCalledWith({
      type: 'OPEN_ADD_NODE_PANEL',
      payload: { sourceNodeId: null, replacementNodeId: null },
    })
  })

  it('renders Run button for existing workflows', () => {
    render(<BuilderEditorToolbar {...defaultProps} />)

    expect(screen.getByRole('button', { name: /^Run$/i })).toBeInTheDocument()
  })

  it('shows disabled Run button for new workflows without triggers', () => {
    render(<BuilderEditorToolbar {...defaultProps} isNew={true} workflow={undefined} />)

    const runButton = screen.getByRole('button', { name: /^Run$/i })
    expect(runButton).toBeInTheDocument()
    expect(runButton).toHaveAttribute('aria-disabled', 'true')
  })

  it('opens run confirmation dialog when Run is clicked', async () => {
    const user = userEvent.setup()
    const dispatch = vi.fn()

    render(
      <BuilderEditorToolbar
        {...defaultProps}
        dispatch={dispatch}
        triggers={[{ id: 'trigger-1', name: 'Test Trigger' }]}
      />
    )

    await user.click(screen.getByRole('button', { name: /^Run$/i }))

    expect(dispatch).toHaveBeenCalledWith({ type: 'SET_CONFIRM_DIALOG', payload: true })
  })

  it('renders workflow details in kebab menu', () => {
    render(<BuilderEditorToolbar {...defaultProps} isKebabOpen={true} />)

    expect(screen.getByRole('menuitem', { name: /Workflow details/i })).toBeInTheDocument()
  })

  it('toggles workflow details when kebab menu item is clicked', async () => {
    const user = userEvent.setup()
    const handleToggleDetails = vi.fn()
    const dispatch = vi.fn()

    render(
      <BuilderEditorToolbar
        {...defaultProps}
        isKebabOpen={true}
        handleToggleDetails={handleToggleDetails}
        dispatch={dispatch}
      />
    )

    await user.click(screen.getByRole('menuitem', { name: /Workflow details/i }))

    expect(handleToggleDetails).toHaveBeenCalledTimes(1)
    expect(dispatch).toHaveBeenCalledWith({ type: 'SET_KEBAB_OPEN', payload: false })
  })

  it('renders run history in kebab menu for existing workflows', () => {
    render(<BuilderEditorToolbar {...defaultProps} isKebabOpen={true} />)

    expect(screen.getByRole('menuitem', { name: /Run history/i })).toBeInTheDocument()
  })

  it('renders version history in kebab menu for existing workflows', () => {
    render(<BuilderEditorToolbar {...defaultProps} isKebabOpen={true} />)

    expect(screen.getByRole('menuitem', { name: /Version history/i })).toBeInTheDocument()
  })

  it('does not render version history in kebab menu for new workflows', () => {
    render(<BuilderEditorToolbar {...defaultProps} isNew={true} workflow={undefined} isKebabOpen={true} />)

    expect(screen.queryByRole('menuitem', { name: /Version history/i })).not.toBeInTheDocument()
  })

  it('toggles version history when kebab menu item is clicked', async () => {
    const user = userEvent.setup()
    const handleToggleVersionHistory = vi.fn()
    const dispatch = vi.fn()

    render(
      <BuilderEditorToolbar
        {...defaultProps}
        isKebabOpen={true}
        handleToggleVersionHistory={handleToggleVersionHistory}
        dispatch={dispatch}
      />
    )

    await user.click(screen.getByRole('menuitem', { name: /Version history/i }))

    expect(handleToggleVersionHistory).toHaveBeenCalledTimes(1)
    expect(dispatch).toHaveBeenCalledWith({ type: 'SET_KEBAB_OPEN', payload: false })
  })

  it('toggles run history when kebab menu item is clicked', async () => {
    const user = userEvent.setup()
    const handleToggleHistory = vi.fn()
    const dispatch = vi.fn()

    render(
      <BuilderEditorToolbar
        {...defaultProps}
        isKebabOpen={true}
        handleToggleHistory={handleToggleHistory}
        dispatch={dispatch}
      />
    )

    await user.click(screen.getByRole('menuitem', { name: /Run history/i }))

    expect(handleToggleHistory).toHaveBeenCalledTimes(1)
    expect(dispatch).toHaveBeenCalledWith({ type: 'SET_KEBAB_OPEN', payload: false })
  })

  it('renders Save button', () => {
    render(<BuilderEditorToolbar {...defaultProps} />)

    expect(screen.getByRole('button', { name: /^Save$/i })).toBeInTheDocument()
  })

  it('calls handleSaveWorkflow when Save is clicked', async () => {
    const user = userEvent.setup()
    const handleSaveWorkflow = vi.fn().mockResolvedValue(true)

    render(<BuilderEditorToolbar {...defaultProps} handleSaveWorkflow={handleSaveWorkflow} />)

    await user.click(screen.getByRole('button', { name: /^Save$/i }))

    expect(handleSaveWorkflow).toHaveBeenCalledTimes(1)
  })

  it('shows Saving... text when save is pending', () => {
    render(<BuilderEditorToolbar {...defaultProps} isPending={true} />)

    expect(screen.getByRole('button', { name: /Saving\.\.\./i })).toBeInTheDocument()
  })

  it('disables Save button when pending', () => {
    render(<BuilderEditorToolbar {...defaultProps} isPending={true} />)

    const saveButton = screen.getByRole('button', { name: /Saving\.\.\./i })
    expect(saveButton).toHaveAttribute('aria-disabled', 'true')
  })

  it('Save button is always clickable for new workflows (validation happens on save, not before)', () => {
    render(<BuilderEditorToolbar {...defaultProps} isNew={true} isDirty={false} workflow={undefined} />)

    const saveButton = screen.getByRole('button', { name: /^Save$/i })
    expect(saveButton).not.toHaveAttribute('aria-disabled', 'true')
  })

  it('disables Save button when there are no unsaved changes', () => {
    render(<BuilderEditorToolbar {...defaultProps} isDirty={false} />)

    const saveButton = screen.getByRole('button', { name: /^Save$/i })
    expect(saveButton).toHaveAttribute('aria-disabled', 'true')
  })

  it('enables Save button when there are unsaved changes', () => {
    render(<BuilderEditorToolbar {...defaultProps} isDirty={true} />)

    const saveButton = screen.getByRole('button', { name: /^Save$/i })
    expect(saveButton).not.toHaveAttribute('aria-disabled', 'true')
  })

  it('shows last saved time in tooltip when hovering Save button', async () => {
    const user = userEvent.setup()
    render(<BuilderEditorToolbar {...defaultProps} isDirty={false} lastSavedAt="2026-01-15T14:30:00Z" />)

    const saveButton = screen.getByRole('button', { name: /^Save$/i })
    await user.hover(saveButton)

    expect(await screen.findByText(/Last saved/)).toBeInTheDocument()
  })

  it('shows last saved time in tooltip even when there are unsaved changes', async () => {
    const user = userEvent.setup()
    render(<BuilderEditorToolbar {...defaultProps} isDirty={true} lastSavedAt="2026-01-15T14:30:00Z" />)

    const saveButton = screen.getByRole('button', { name: /^Save$/i })
    await user.hover(saveButton)

    expect(await screen.findByText(/Last saved/)).toBeInTheDocument()
  })

  it('shows "Save workflow" tooltip when workflow has never been saved', async () => {
    const user = userEvent.setup()
    render(<BuilderEditorToolbar {...defaultProps} isDirty={true} lastSavedAt={undefined} />)

    const saveButton = screen.getByRole('button', { name: /^Save$/i })
    await user.hover(saveButton)

    expect(await screen.findByText('Save workflow')).toBeInTheDocument()
  })

  it('renders Publish button for existing workflows', () => {
    render(<BuilderEditorToolbar {...defaultProps} />)

    expect(screen.getByRole('button', { name: /Publish/i })).toBeInTheDocument()
  })

  it('does not render Publish button for new workflows', () => {
    render(<BuilderEditorToolbar {...defaultProps} isNew={true} workflow={undefined} />)

    expect(screen.queryByRole('button', { name: /Publish/i })).not.toBeInTheDocument()
  })

  it('calls onPublishClick when Publish button is clicked', async () => {
    const user = userEvent.setup()
    const onPublishClick = vi.fn()

    render(<BuilderEditorToolbar {...defaultProps} onPublishClick={onPublishClick} />)

    await user.click(screen.getByRole('button', { name: /Publish/i }))

    expect(onPublishClick).toHaveBeenCalledTimes(1)
  })

  it('renders Unpublish in kebab menu when workflow is published', () => {
    render(<BuilderEditorToolbar {...defaultProps} isKebabOpen={true} publishedVersionId="ver-2" />)

    expect(screen.getByRole('menuitem', { name: /Unpublish workflow/i })).toBeInTheDocument()
  })

  it('does not render Unpublish when workflow is not published', () => {
    render(<BuilderEditorToolbar {...defaultProps} isKebabOpen={true} publishedVersionId={null} />)

    expect(screen.queryByRole('menuitem', { name: /Unpublish workflow/i })).not.toBeInTheDocument()
  })

  it('renders delete workflow menu when kebab is open', () => {
    render(<BuilderEditorToolbar {...defaultProps} isKebabOpen={true} />)

    expect(screen.getByRole('menuitem', { name: /Delete workflow/i })).toBeInTheDocument()
  })

  it('opens delete dialog when delete menu item is clicked', async () => {
    const user = userEvent.setup()
    const dispatch = vi.fn()

    render(<BuilderEditorToolbar {...defaultProps} isKebabOpen={true} dispatch={dispatch} />)

    const deleteMenuItem = screen.getByRole('menuitem', { name: /Delete workflow/i })
    await user.click(deleteMenuItem)

    expect(dispatch).toHaveBeenCalledWith({ type: 'SET_DELETE_DIALOG', payload: true })
    expect(dispatch).toHaveBeenCalledWith({ type: 'SET_KEBAB_OPEN', payload: false })
  })

  it('renders kebab menu but not delete for new workflows', () => {
    render(<BuilderEditorToolbar {...defaultProps} isNew={true} workflow={undefined} isKebabOpen={true} />)

    expect(screen.getByRole('button', { name: /Workflow actions/i })).toBeInTheDocument()
    expect(screen.queryByRole('menuitem', { name: /Delete workflow/i })).not.toBeInTheDocument()
    expect(screen.getByRole('menuitem', { name: /Export workflow/i })).toBeInTheDocument()
    expect(screen.getByRole('menuitem', { name: /Import workflow/i })).toBeInTheDocument()
  })

  describe('permission-denied states', () => {
    const deniedPermissions = (overrides: Partial<typeof defaultProps.builderPermissions>) => ({
      ...defaultProps.builderPermissions,
      ...overrides,
      tooltips: { ...defaultProps.builderPermissions.tooltips, ...overrides.tooltips },
    })

    it('disables Add step, Save, and Publish when canEdit is false', () => {
      render(<BuilderEditorToolbar {...defaultProps} builderPermissions={deniedPermissions({ canEdit: false })} />)

      expect(screen.getByRole('button', { name: /Add step/i })).toHaveAttribute('aria-disabled', 'true')
      expect(screen.getByRole('button', { name: /^Save$/i })).toHaveAttribute('aria-disabled', 'true')
      expect(screen.getByRole('button', { name: /Publish/i })).toHaveAttribute('aria-disabled', 'true')
    })

    it('does not fire handlers when canEdit is false', async () => {
      const user = userEvent.setup()
      const dispatch = vi.fn()
      const handleSaveWorkflow = vi.fn()
      const onPublishClick = vi.fn()

      render(
        <BuilderEditorToolbar
          {...defaultProps}
          dispatch={dispatch}
          handleSaveWorkflow={handleSaveWorkflow}
          onPublishClick={onPublishClick}
          builderPermissions={deniedPermissions({ canEdit: false })}
        />
      )

      await user.click(screen.getByRole('button', { name: /Add step/i }))
      await user.click(screen.getByRole('button', { name: /^Save$/i }))
      await user.click(screen.getByRole('button', { name: /Publish/i }))

      expect(dispatch).not.toHaveBeenCalledWith(expect.objectContaining({ type: 'OPEN_ADD_NODE_PANEL' }))
      expect(handleSaveWorkflow).not.toHaveBeenCalled()
      expect(onPublishClick).not.toHaveBeenCalled()
    })

    it('disables Run button when canRun is false', () => {
      render(<BuilderEditorToolbar {...defaultProps} builderPermissions={deniedPermissions({ canRun: false })} />)

      expect(screen.getByRole('button', { name: /^Run$/i })).toHaveAttribute('aria-disabled', 'true')
    })

    it('disables Run button when isNodeEditorOpen is true', () => {
      render(<BuilderEditorToolbar {...defaultProps} isNodeEditorOpen />)

      expect(screen.getByRole('button', { name: /^Run$/i })).toHaveAttribute('aria-disabled', 'true')
    })

    it('disables Delete menu item when canDelete is false', () => {
      render(
        <BuilderEditorToolbar
          {...defaultProps}
          isKebabOpen
          builderPermissions={deniedPermissions({ canDelete: false })}
        />
      )

      expect(screen.getByRole('menuitem', { name: /Delete workflow/i })).toHaveAttribute('aria-disabled', 'true')
    })
  })

  it('returns null for read-only empty new builder', () => {
    const { container } = render(
      <BuilderEditorToolbar
        {...defaultProps}
        isNew
        hasNoWorkflowNodes
        workflow={undefined}
        builderPermissions={{
          ...defaultProps.builderPermissions,
          canEdit: false,
        }}
      />
    )

    expect(container).toBeEmptyDOMElement()
  })

  describe('multi-trigger run dropdown', () => {
    const multiTriggerProps = {
      ...defaultProps,
      triggers: [
        { id: 'trigger-1', name: 'HTTP Webhook' },
        { id: 'trigger-2', name: 'Scheduled' },
      ],
    }

    it('renders dropdown toggle for multiple triggers', () => {
      render(<BuilderEditorToolbar {...multiTriggerProps} />)

      expect(screen.getByRole('button', { name: /Run workflow/i })).toBeInTheDocument()
    })

    it('shows trigger options when dropdown is clicked', async () => {
      const user = userEvent.setup()
      render(<BuilderEditorToolbar {...multiTriggerProps} />)

      await user.click(screen.getByRole('button', { name: /Run workflow/i }))

      expect(screen.getByRole('menuitem', { name: 'HTTP Webhook' })).toBeInTheDocument()
      expect(screen.getByRole('menuitem', { name: 'Scheduled' })).toBeInTheDocument()
    })

    it('dispatches trigger selection and opens confirm dialog', async () => {
      const user = userEvent.setup()
      const dispatch = vi.fn()

      render(<BuilderEditorToolbar {...multiTriggerProps} dispatch={dispatch} />)

      await user.click(screen.getByRole('button', { name: /Run workflow/i }))
      await user.click(screen.getByRole('menuitem', { name: 'HTTP Webhook' }))

      expect(dispatch).toHaveBeenCalledWith({ type: 'SET_SELECTED_TRIGGER', payload: 0 })
      expect(dispatch).toHaveBeenCalledWith({ type: 'SET_CONFIRM_DIALOG', payload: true })
    })

    it('disables run dropdown when canRun is false', () => {
      render(
        <BuilderEditorToolbar
          {...multiTriggerProps}
          builderPermissions={{ ...defaultProps.builderPermissions, canRun: false }}
        />
      )

      expect(screen.getByRole('button', { name: /Run workflow/i })).toBeDisabled()
    })

    it('uses fallback name for triggers without a name', async () => {
      const user = userEvent.setup()
      render(<BuilderEditorToolbar {...defaultProps} triggers={[{ id: 'trigger-1' }, { id: 'trigger-2' }]} />)

      await user.click(screen.getByRole('button', { name: /Run workflow/i }))

      expect(screen.getByRole('menuitem', { name: 'Trigger 1' })).toBeInTheDocument()
      expect(screen.getByRole('menuitem', { name: 'Trigger 2' })).toBeInTheDocument()
    })
  })

  describe('kebab menu disabled states', () => {
    it('disables Import workflow when canEdit is false', () => {
      render(
        <BuilderEditorToolbar
          {...defaultProps}
          isKebabOpen
          builderPermissions={{ ...defaultProps.builderPermissions, canEdit: false }}
        />
      )

      expect(screen.getByRole('menuitem', { name: /Import workflow/i })).toHaveAttribute('aria-disabled', 'true')
    })

    it('disables Unpublish workflow when canEdit is false', () => {
      render(
        <BuilderEditorToolbar
          {...defaultProps}
          isKebabOpen
          publishedVersionId="ver-2"
          builderPermissions={{ ...defaultProps.builderPermissions, canEdit: false }}
        />
      )

      expect(screen.getByRole('menuitem', { name: /Unpublish workflow/i })).toHaveAttribute('aria-disabled', 'true')
    })

    it('does not fire Import handler when canEdit is false', async () => {
      const user = userEvent.setup()
      const markDirty = vi.fn()

      render(
        <BuilderEditorToolbar
          {...defaultProps}
          isKebabOpen
          markDirty={markDirty}
          builderPermissions={{ ...defaultProps.builderPermissions, canEdit: false }}
        />
      )

      await user.click(screen.getByRole('menuitem', { name: /Import workflow/i }))

      expect(markDirty).not.toHaveBeenCalled()
    })

    it('does not fire Unpublish handler when canEdit is false', async () => {
      const user = userEvent.setup()
      const onUnpublish = vi.fn()

      render(
        <BuilderEditorToolbar
          {...defaultProps}
          isKebabOpen
          publishedVersionId="ver-2"
          onUnpublish={onUnpublish}
          builderPermissions={{ ...defaultProps.builderPermissions, canEdit: false }}
        />
      )

      await user.click(screen.getByRole('menuitem', { name: /Unpublish workflow/i }))

      expect(onUnpublish).not.toHaveBeenCalled()
    })

    it('does not fire Delete handler when canDelete is false', async () => {
      const user = userEvent.setup()
      const dispatch = vi.fn()

      render(
        <BuilderEditorToolbar
          {...defaultProps}
          isKebabOpen
          dispatch={dispatch}
          builderPermissions={{ ...defaultProps.builderPermissions, canDelete: false }}
        />
      )

      await user.click(screen.getByRole('menuitem', { name: /Delete workflow/i }))

      expect(dispatch).not.toHaveBeenCalledWith(expect.objectContaining({ type: 'SET_DELETE_DIALOG' }))
    })

    it('removes danger styling from Delete when canDelete is false', () => {
      render(
        <BuilderEditorToolbar
          {...defaultProps}
          isKebabOpen
          builderPermissions={{ ...defaultProps.builderPermissions, canDelete: false }}
        />
      )

      const deleteItem = screen.getByRole('menuitem', { name: /Delete workflow/i })
      expect(deleteItem).not.toHaveClass('pf-m-danger')
    })
  })

  it('fires Export handler when clicked', async () => {
    const user = userEvent.setup()

    render(<BuilderEditorToolbar {...defaultProps} isKebabOpen />)

    await user.click(screen.getByRole('menuitem', { name: /Export workflow/i }))

    expect(mockHandleExport).toHaveBeenCalledTimes(1)
  })

  it('fires Unpublish handler when canEdit is true', async () => {
    const user = userEvent.setup()
    const onUnpublish = vi.fn()
    const dispatch = vi.fn()

    render(
      <BuilderEditorToolbar
        {...defaultProps}
        isKebabOpen
        publishedVersionId="ver-2"
        onUnpublish={onUnpublish}
        dispatch={dispatch}
      />
    )

    await user.click(screen.getByRole('menuitem', { name: /Unpublish workflow/i }))

    expect(onUnpublish).toHaveBeenCalledTimes(1)
    expect(dispatch).toHaveBeenCalledWith({ type: 'SET_KEBAB_OPEN', payload: false })
  })

  it('fires Import file input click when canEdit is true', async () => {
    const user = userEvent.setup()
    const dispatch = vi.fn()

    render(<BuilderEditorToolbar {...defaultProps} isKebabOpen dispatch={dispatch} />)

    await user.click(screen.getByRole('menuitem', { name: /Import workflow/i }))

    expect(dispatch).toHaveBeenCalledWith({ type: 'SET_KEBAB_OPEN', payload: false })
  })

  it('does not fire Run handler when canRun is false', async () => {
    const user = userEvent.setup()
    const dispatch = vi.fn()

    render(
      <BuilderEditorToolbar
        {...defaultProps}
        builderPermissions={{ ...defaultProps.builderPermissions, canRun: false }}
        dispatch={dispatch}
      />
    )

    await user.click(screen.getByRole('button', { name: /^Run$/i }))

    expect(dispatch).not.toHaveBeenCalledWith(expect.objectContaining({ type: 'SET_CONFIRM_DIALOG' }))
  })

  it('shows permission-denied tooltip on Save when canEdit is false', async () => {
    const user = userEvent.setup()
    render(
      <BuilderEditorToolbar
        {...defaultProps}
        builderPermissions={{
          ...defaultProps.builderPermissions,
          canEdit: false,
          tooltips: { ...defaultProps.builderPermissions.tooltips, save: 'No save permission' },
        }}
      />
    )

    await user.hover(screen.getByRole('button', { name: /^Save$/i }))

    expect(await screen.findByText('No save permission')).toBeInTheDocument()
  })

  describe('Duplicate workflow action', () => {
    it('renders Duplicate workflow in kebab menu for existing workflows', () => {
      render(<BuilderEditorToolbar {...defaultProps} isKebabOpen />)

      expect(screen.getByRole('menuitem', { name: /Duplicate workflow/i })).toBeInTheDocument()
    })

    it('does not render Duplicate for new workflows', () => {
      render(<BuilderEditorToolbar {...defaultProps} isNew workflow={undefined} isKebabOpen />)

      expect(screen.queryByRole('menuitem', { name: /Duplicate workflow/i })).not.toBeInTheDocument()
    })

    it('positions Duplicate between Verify and Export', () => {
      render(<BuilderEditorToolbar {...defaultProps} isKebabOpen />)

      const menuItems = screen.getAllByRole('menuitem')
      const verifyIndex = menuItems.findIndex((item) => item.textContent?.includes('Verify'))
      const duplicateIndex = menuItems.findIndex((item) => item.textContent?.includes('Duplicate'))
      const exportIndex = menuItems.findIndex((item) => item.textContent?.includes('Export'))

      expect(duplicateIndex).toBeGreaterThan(verifyIndex)
      expect(duplicateIndex).toBeLessThan(exportIndex)
    })

    it('fires onDuplicate handler when clicked', async () => {
      const user = userEvent.setup()
      const dispatch = vi.fn()
      const onDuplicate = vi.fn()

      render(<BuilderEditorToolbar {...defaultProps} isKebabOpen dispatch={dispatch} onDuplicate={onDuplicate} />)

      await user.click(screen.getByRole('menuitem', { name: /Duplicate workflow/i }))

      expect(onDuplicate).toHaveBeenCalledTimes(1)
      expect(dispatch).toHaveBeenCalledWith({ type: 'SET_KEBAB_OPEN', payload: false })
    })

    it('disables Duplicate when canCreate is false', () => {
      render(
        <BuilderEditorToolbar
          {...defaultProps}
          isKebabOpen
          builderPermissions={{ ...defaultProps.builderPermissions, canCreate: false }}
        />
      )

      expect(screen.getByRole('menuitem', { name: /Duplicate workflow/i })).toHaveAttribute('aria-disabled', 'true')
    })

    it('does not fire onDuplicate when canCreate is false', async () => {
      const user = userEvent.setup()
      const onDuplicate = vi.fn()

      render(
        <BuilderEditorToolbar
          {...defaultProps}
          isKebabOpen
          onDuplicate={onDuplicate}
          builderPermissions={{ ...defaultProps.builderPermissions, canCreate: false }}
        />
      )

      await user.click(screen.getByRole('menuitem', { name: /Duplicate workflow/i }))

      expect(onDuplicate).not.toHaveBeenCalled()
    })

    it('shows permission tooltip when canCreate is false', async () => {
      const user = userEvent.setup()

      render(
        <BuilderEditorToolbar
          {...defaultProps}
          isKebabOpen
          builderPermissions={{
            ...defaultProps.builderPermissions,
            canCreate: false,
            tooltips: { ...defaultProps.builderPermissions.tooltips, create: 'No create permission' },
          }}
        />
      )

      await user.hover(screen.getByRole('menuitem', { name: /Duplicate workflow/i }))

      expect(await screen.findByText('No create permission')).toBeInTheDocument()
    })
  })

  it('has no accessibility violations', async () => {
    const { container } = render(<BuilderEditorToolbar {...defaultProps} />)

    expect(await axe(container)).toHaveNoViolations()
  })

  it('has no accessibility violations for new workflow', async () => {
    const { container } = render(<BuilderEditorToolbar {...defaultProps} isNew={true} workflow={undefined} />)

    expect(await axe(container)).toHaveNoViolations()
  })

  describe('re-render memoization paths', () => {
    it('handles re-render with same props', () => {
      const { rerender } = render(<BuilderEditorToolbar {...defaultProps} />)
      rerender(<BuilderEditorToolbar {...defaultProps} />)

      expect(screen.getByRole('button', { name: /Add step/i })).toBeInTheDocument()
      expect(screen.getByRole('button', { name: /^Run$/i })).toBeInTheDocument()
      expect(screen.getByRole('button', { name: /^Save$/i })).toBeInTheDocument()
    })

    it('handles re-render with kebab open', () => {
      const props = { ...defaultProps, isKebabOpen: true, publishedVersionId: 'ver-2' }
      const { rerender } = render(<BuilderEditorToolbar {...props} />)
      rerender(<BuilderEditorToolbar {...props} />)

      expect(screen.getByRole('menuitem', { name: /Run history/i })).toBeInTheDocument()
      expect(screen.getByRole('menuitem', { name: /Unpublish workflow/i })).toBeInTheDocument()
      expect(screen.getByRole('menuitem', { name: /Delete workflow/i })).toBeInTheDocument()
    })

    it('handles re-render with multi-trigger dropdown', () => {
      const props = {
        ...defaultProps,
        triggers: [
          { id: 't-1', name: 'A' },
          { id: 't-2', name: 'B' },
        ],
      }
      const { rerender } = render(<BuilderEditorToolbar {...props} />)
      rerender(<BuilderEditorToolbar {...props} />)

      expect(screen.getByRole('button', { name: /Run workflow/i })).toBeInTheDocument()
    })

    it('handles re-render with permissions denied', () => {
      const props = {
        ...defaultProps,
        builderPermissions: {
          ...defaultProps.builderPermissions,
          canEdit: false,
          canRun: false,
          canDelete: false,
        },
      }
      const { rerender } = render(<BuilderEditorToolbar {...props} />)
      rerender(<BuilderEditorToolbar {...props} />)

      expect(screen.getByRole('button', { name: /Add step/i })).toHaveAttribute('aria-disabled', 'true')
    })

    it('handles re-render for new workflow', () => {
      const props = { ...defaultProps, isNew: true, workflow: undefined }
      const { rerender } = render(<BuilderEditorToolbar {...props} />)
      rerender(<BuilderEditorToolbar {...props} />)

      expect(screen.getByRole('button', { name: /^Save$/i })).toBeInTheDocument()
    })

    it('handles prop change from editable to read-only', () => {
      const { rerender } = render(<BuilderEditorToolbar {...defaultProps} />)
      rerender(
        <BuilderEditorToolbar
          {...defaultProps}
          builderPermissions={{ ...defaultProps.builderPermissions, canEdit: false }}
        />
      )

      expect(screen.getByRole('button', { name: /Add step/i })).toHaveAttribute('aria-disabled', 'true')
    })

    it('handles prop change from clean to dirty', () => {
      const { rerender } = render(<BuilderEditorToolbar {...defaultProps} isDirty={false} />)
      rerender(<BuilderEditorToolbar {...defaultProps} isDirty />)

      expect(screen.getByRole('button', { name: /^Save$/i })).not.toHaveAttribute('aria-disabled', 'true')
    })
  })

  describe('compound condition branch coverage', () => {
    it('shows disabled Run and hides Publish when workflow is undefined for existing route', () => {
      render(<BuilderEditorToolbar {...defaultProps} isNew={false} workflow={undefined} />)

      const runButton = screen.getByRole('button', { name: /^Run$/i })
      expect(runButton).toBeInTheDocument()
      expect(runButton).toHaveAttribute('aria-disabled', 'true')
      expect(screen.queryByRole('button', { name: /Publish/i })).not.toBeInTheDocument()
      expect(screen.getByRole('button', { name: /Add step/i })).toBeInTheDocument()
      expect(screen.getByRole('button', { name: /^Save$/i })).toBeInTheDocument()
    })

    it('hides Run history, Delete, and Unpublish in kebab when workflow is undefined', () => {
      render(
        <BuilderEditorToolbar
          {...defaultProps}
          isNew={false}
          workflow={undefined}
          isKebabOpen
          publishedVersionId="ver-2"
        />
      )

      expect(screen.queryByRole('menuitem', { name: /Run history/i })).not.toBeInTheDocument()
      expect(screen.queryByRole('menuitem', { name: /Delete workflow/i })).not.toBeInTheDocument()
      expect(screen.queryByRole('menuitem', { name: /Unpublish workflow/i })).not.toBeInTheDocument()
      expect(screen.getByRole('menuitem', { name: /Export workflow/i })).toBeInTheDocument()
      expect(screen.getByRole('menuitem', { name: /Import workflow/i })).toBeInTheDocument()
    })

    it('renders Run and Publish without Add step when existing workflow has no nodes', () => {
      render(<BuilderEditorToolbar {...defaultProps} isNew={false} workflow={{ id: 'wf-1' }} hasNoWorkflowNodes />)

      expect(screen.queryByRole('button', { name: /Add step/i })).not.toBeInTheDocument()
      expect(screen.getByRole('button', { name: /^Run$/i })).toBeInTheDocument()
      expect(screen.getByRole('button', { name: /Publish/i })).toBeInTheDocument()
      expect(screen.getByRole('button', { name: /^Save$/i })).toBeInTheDocument()
    })

    it('renders toolbar when canEdit is false and hasNoWorkflowNodes is true but isNew is false', () => {
      const { container } = render(
        <BuilderEditorToolbar
          {...defaultProps}
          isNew={false}
          workflow={{ id: 'wf-1' }}
          hasNoWorkflowNodes
          builderPermissions={{ ...defaultProps.builderPermissions, canEdit: false }}
        />
      )

      expect(container).not.toBeEmptyDOMElement()
      expect(screen.getByRole('button', { name: /^Run$/i })).toBeInTheDocument()
    })

    it('renders toolbar when canEdit is false and isNew is true but hasNoWorkflowNodes is false', () => {
      const { container } = render(
        <BuilderEditorToolbar
          {...defaultProps}
          isNew
          hasNoWorkflowNodes={false}
          workflow={undefined}
          builderPermissions={{ ...defaultProps.builderPermissions, canEdit: false }}
        />
      )

      expect(container).not.toBeEmptyDOMElement()
      expect(screen.getByRole('button', { name: /Add step/i })).toBeInTheDocument()
    })

    it('toggles kebab dropdown when toggle is clicked', async () => {
      const user = userEvent.setup()
      const dispatch = vi.fn()

      render(<BuilderEditorToolbar {...defaultProps} isKebabOpen={false} dispatch={dispatch} />)

      await user.click(screen.getByRole('button', { name: /Workflow actions/i }))

      expect(dispatch).toHaveBeenCalledWith({ type: 'SET_KEBAB_OPEN', payload: true })
    })

    it('renders single trigger with explicit triggers array of length 1', () => {
      render(<BuilderEditorToolbar {...defaultProps} triggers={[{ id: 'trigger-1', name: 'Webhook' }]} />)

      expect(screen.getByRole('button', { name: /^Run$/i })).toBeInTheDocument()
      expect(screen.queryByRole('button', { name: /Run workflow/i })).not.toBeInTheDocument()
    })

    it('renders save tooltip when lastSavedAt is null', async () => {
      const user = userEvent.setup()
      render(<BuilderEditorToolbar {...defaultProps} isDirty lastSavedAt={null} />)

      await user.hover(screen.getByRole('button', { name: /^Save$/i }))

      expect(await screen.findByText('Save workflow')).toBeInTheDocument()
    })

    it('shows all kebab items for published existing workflow', () => {
      render(
        <BuilderEditorToolbar
          {...defaultProps}
          isNew={false}
          workflow={{ id: 'wf-1' }}
          isKebabOpen
          publishedVersionId="ver-3"
        />
      )

      expect(screen.getByRole('menuitem', { name: /Run history/i })).toBeInTheDocument()
      expect(screen.getByRole('menuitem', { name: /Unpublish workflow/i })).toBeInTheDocument()
      expect(screen.getByRole('menuitem', { name: /Delete workflow/i })).toBeInTheDocument()
      expect(screen.getByRole('menuitem', { name: /Export workflow/i })).toBeInTheDocument()
      expect(screen.getByRole('menuitem', { name: /Import workflow/i })).toBeInTheDocument()
    })

    it('disables kebab items when canEdit and canDelete are both false', () => {
      render(
        <BuilderEditorToolbar
          {...defaultProps}
          isKebabOpen
          publishedVersionId="ver-2"
          builderPermissions={{ ...defaultProps.builderPermissions, canEdit: false, canDelete: false }}
        />
      )

      expect(screen.getByRole('menuitem', { name: /Import workflow/i })).toHaveAttribute('aria-disabled', 'true')
      expect(screen.getByRole('menuitem', { name: /Unpublish workflow/i })).toHaveAttribute('aria-disabled', 'true')
      expect(screen.getByRole('menuitem', { name: /Delete workflow/i })).toHaveAttribute('aria-disabled', 'true')
      expect(screen.getByRole('menuitem', { name: /Export workflow/i })).not.toHaveAttribute('aria-disabled', 'true')
    })

    it('does not render Run dropdown when canRun is false with multiple triggers', async () => {
      const user = userEvent.setup()
      const dispatch = vi.fn()

      render(
        <BuilderEditorToolbar
          {...defaultProps}
          triggers={[
            { id: 't-1', name: 'Trigger A' },
            { id: 't-2', name: 'Trigger B' },
          ]}
          dispatch={dispatch}
          builderPermissions={{ ...defaultProps.builderPermissions, canRun: false }}
        />
      )

      await user.click(screen.getByRole('button', { name: /Run workflow/i }))

      expect(screen.queryByRole('menuitem', { name: 'Trigger A' })).not.toBeInTheDocument()
    })

    it('renders dividers correctly for existing workflow with nodes', () => {
      render(
        <BuilderEditorToolbar {...defaultProps} isNew={false} workflow={{ id: 'wf-1' }} hasNoWorkflowNodes={false} />
      )

      expect(screen.getAllByRole('separator').length).toBeGreaterThanOrEqual(3)
    })

    it('renders fewer dividers for new workflow without nodes', () => {
      render(
        <BuilderEditorToolbar
          {...defaultProps}
          isNew
          workflow={undefined}
          hasNoWorkflowNodes
          builderPermissions={{ ...defaultProps.builderPermissions, canEdit: true }}
        />
      )

      const separators = screen.getAllByRole('separator')
      expect(separators.length).toBeLessThanOrEqual(2)
    })
  })

  describe('verify-then-publish with error gating', () => {
    it('triggers verification when Publish button is clicked', async () => {
      const user = userEvent.setup()

      render(<BuilderEditorToolbar {...defaultProps} />)

      await user.click(screen.getByRole('button', { name: /Publish/i }))

      expect(mockHandleVerify).toHaveBeenCalledTimes(1)
      expect(mockHandleVerify).toHaveBeenCalledWith(expect.any(Function))
    })

    it('disables Publish button when validationErrorCount > 0', () => {
      mockValidationErrorCount = 3

      render(<BuilderEditorToolbar {...defaultProps} />)

      expect(screen.getByRole('button', { name: /Publish/i })).toHaveAttribute('aria-disabled', 'true')
    })

    it('shows error tooltip when Publish is disabled by validation errors', async () => {
      const user = userEvent.setup()
      mockValidationErrorCount = 3

      render(<BuilderEditorToolbar {...defaultProps} />)

      await user.hover(screen.getByRole('button', { name: /Publish/i }))

      expect(await screen.findByText('Verify your workflow before publishing — 3 errors found')).toBeInTheDocument()
    })

    it('shows permission tooltip when Publish is disabled by canEdit', async () => {
      const user = userEvent.setup()

      render(
        <BuilderEditorToolbar
          {...defaultProps}
          builderPermissions={{
            ...defaultProps.builderPermissions,
            canEdit: false,
            tooltips: { ...defaultProps.builderPermissions.tooltips, publish: 'No publish permission' },
          }}
        />
      )

      await user.hover(screen.getByRole('button', { name: /Publish/i }))

      expect(await screen.findByText('No publish permission')).toBeInTheDocument()
    })

    it('disables Publish button while isVerifying is true', () => {
      mockIsVerifying = true

      render(<BuilderEditorToolbar {...defaultProps} />)

      expect(screen.getByRole('button', { name: /Publish/i })).toHaveAttribute('aria-disabled', 'true')
    })

    it('does not fire onPublishClick when validationErrorCount > 0', async () => {
      const user = userEvent.setup()
      const onPublishClick = vi.fn()
      mockValidationErrorCount = 3

      render(<BuilderEditorToolbar {...defaultProps} onPublishClick={onPublishClick} />)

      await user.click(screen.getByRole('button', { name: /Publish/i }))

      expect(onPublishClick).not.toHaveBeenCalled()
    })

    it('does not fire onPublishClick directly without verification', async () => {
      const user = userEvent.setup()
      const onPublishClick = vi.fn()
      mockHandleVerify.mockImplementation(() => {})

      render(<BuilderEditorToolbar {...defaultProps} onPublishClick={onPublishClick} />)

      await user.click(screen.getByRole('button', { name: /Publish/i }))

      expect(mockHandleVerify).toHaveBeenCalledTimes(1)
      expect(onPublishClick).not.toHaveBeenCalled()
    })

    it('kebab Verify workflow does not pass event as callback', async () => {
      const user = userEvent.setup()

      render(<BuilderEditorToolbar {...defaultProps} isKebabOpen />)

      await user.click(screen.getByRole('menuitem', { name: /Verify workflow/i }))

      expect(mockHandleVerify).toHaveBeenCalledTimes(1)
      expect(mockHandleVerify).toHaveBeenCalledWith()
    })
  })
})
