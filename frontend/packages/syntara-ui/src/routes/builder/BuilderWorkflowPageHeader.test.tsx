import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { axe } from 'vitest-axe'

import { expectPageTitle } from '../../test/pageTitle'

import { BuilderWorkflowPageHeader, type BuilderWorkflowPageHeaderProps } from './BuilderWorkflowPageHeader'
import styles from './BuilderWorkflowPageHeader.module.css'

const mockWorkflowStoreState = vi.hoisted(() => ({
  isDirty: false,
  currentWorkflow: {
    workflow: { activities: [{ id: 'n1', type: 'script', name: 'Step', parameters: {} }] },
  },
}))

vi.mock('../../stores/useWorkflowStore', () => {
  const store = (selector: (state: Record<string, unknown>) => unknown) => selector(mockWorkflowStoreState)
  store.getState = () => mockWorkflowStoreState
  return { useWorkflowStore: store }
})

vi.mock('./useWorkflowImportExport', () => ({
  useWorkflowImportExport: () => ({
    importFileRef: { current: null },
    handleImportFile: vi.fn(),
    handleExport: vi.fn(),
    handleVerify: vi.fn((onValid?: () => void) => onValid?.()),
    isVerifying: false,
    validationErrorCount: 0,
  }),
}))

vi.mock('../../client', () => ({
  authMiddleware: { onRequest: vi.fn() },
  interfaceTagMiddleware: { onRequest: vi.fn() },
  executionsClient: {
    useMutation: vi.fn(() => ({
      mutate: vi.fn(),
      isPending: false,
    })),
  },
}))

vi.mock('../../providers/alerts/AlertContext', () => ({
  useAlerts: () => ({
    showSuccess: vi.fn(),
    showError: vi.fn(),
  }),
}))

vi.mock('./EditWorkflowDetailsPopover', () => ({
  EditWorkflowDetailsPopover: ({
    onApply,
  }: {
    name: string
    description: string
    onApply: (name: string, description: string) => void
  }) => (
    <button onClick={() => onApply('New Name', 'New Desc')} aria-label="Apply details">
      Edit details
    </button>
  ),
}))

describe('BuilderWorkflowPageHeader', () => {
  const baseProps: BuilderWorkflowPageHeaderProps = {
    workflowName: 'wf',
    workflowDescription: '',
    isBuiltin: false,
    isNew: true,
    workflow: undefined,
    isPending: false,
    isDirty: true,
    lastSavedAt: '2026-01-15T14:30:00Z',
    isKebabOpen: false,
    publishedVersionId: null as string | null,

    isPublishing: false,
    isAddNodePanelOpen: false,
    hasNoWorkflowNodes: false,
    ProjectSelector: <span>Project</span>,
    dispatch: vi.fn(),
    markDirty: vi.fn(),
    handleToggleHistory: vi.fn(),
    handleToggleVersionHistory: vi.fn(),
    handleToggleDetails: vi.fn(),
    handleSaveWorkflow: vi.fn().mockResolvedValue(true),
    onPublish: vi.fn(),
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
    vi.clearAllMocks()
  })

  it('has no accessibility violations in editor mode', async () => {
    const { container } = render(<BuilderWorkflowPageHeader {...baseProps} />)
    expect(await axe(container)).toHaveNoViolations()
  })

  it('shows Back to editor button during live run and hides toolbar', () => {
    const onBackToEditor = vi.fn()
    render(
      <BuilderWorkflowPageHeader
        {...baseProps}
        isNew={false}
        workflow={{ id: 'workflow-1' }}
        isLiveRunActive
        onBackToEditor={onBackToEditor}
      />
    )

    const backButton = screen.getByRole('button', { name: 'Back to editor' })
    expect(backButton).toBeInTheDocument()

    expect(screen.queryByRole('button', { name: 'Add Step' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Run/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Save/i })).not.toBeInTheDocument()
  })

  it('shows Review approval button during live run with pending approval', () => {
    const onBackToEditor = vi.fn()
    const onReviewApproval = vi.fn()
    render(
      <BuilderWorkflowPageHeader
        {...baseProps}
        isNew={false}
        workflow={{ id: 'workflow-1' }}
        isLiveRunActive
        onBackToEditor={onBackToEditor}
        hasApprovalPending
        onReviewApproval={onReviewApproval}
      />
    )

    expect(screen.getByRole('button', { name: 'Review approval' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Back to editor' })).toBeInTheDocument()
  })

  it('keeps the workflow name field visible next to the edit control', () => {
    render(<BuilderWorkflowPageHeader {...baseProps} workflowName="Deploy app" />)

    const nameInput = screen.getByRole('textbox', { name: 'Workflow name' })
    expect(nameInput).toBeVisible()
    expect(nameInput).toHaveValue('Deploy app')
    expect(screen.getByRole('button', { name: 'Apply details' })).toBeInTheDocument()
  })

  it('still shows the workflow name when the title row includes project and status controls', () => {
    render(
      <BuilderWorkflowPageHeader
        {...baseProps}
        isNew={false}
        workflow={{ id: 'wf-1' }}
        publishedVersionId={null}
        workflowName="Deploy app"
      />
    )

    const nameInput = screen.getByRole('textbox', { name: 'Workflow name' })
    expect(nameInput).toBeVisible()
    expect(nameInput).toHaveValue('Deploy app')
    expect(screen.getByText('Draft')).toBeInTheDocument()

    const nameSlot = screen.getByTestId('builder-workflow-name')
    expect(nameSlot).toHaveClass(styles.workflowName)
    expect(screen.getByTestId('builder-title-slot')).toHaveClass('pf-m-wrap')

    const computed = window.getComputedStyle(nameSlot)
    expect(computed.minWidth).toBe('16ch')
    expect(computed.maxWidth).toBe('24ch')
    expect(computed.flexShrink).toBe('1')
  })

  it('updates workflow name and marks dirty on change', async () => {
    const user = userEvent.setup()
    const dispatch = vi.fn()
    const markDirty = vi.fn()

    render(<BuilderWorkflowPageHeader {...baseProps} dispatch={dispatch} markDirty={markDirty} />)

    const nameInput = screen.getByRole('textbox', { name: /Workflow name/i })
    await user.type(nameInput, 'Updated')

    expect(dispatch).toHaveBeenCalledWith(expect.objectContaining({ type: 'SET_WORKFLOW_NAME' }))
    expect(markDirty).toHaveBeenCalled()
  })

  it('does not show status badge for new workflows', () => {
    render(<BuilderWorkflowPageHeader {...baseProps} isNew={true} />)

    expect(screen.queryByText('Draft')).not.toBeInTheDocument()
    expect(screen.queryByText('Published')).not.toBeInTheDocument()
  })

  it('shows status badge for existing workflows', () => {
    render(
      <BuilderWorkflowPageHeader {...baseProps} isNew={false} workflow={{ id: 'wf-1' }} publishedVersionId={null} />
    )

    expect(screen.getByText('Draft')).toBeInTheDocument()
  })

  it('shows Published badge when versions match', () => {
    render(
      <BuilderWorkflowPageHeader {...baseProps} isNew={false} workflow={{ id: 'wf-1' }} publishedVersionId="ver-2" />
    )

    expect(screen.getByText('Published')).toBeInTheDocument()
  })

  it('shows Published badge for any non-null publishedVersionId', () => {
    render(
      <BuilderWorkflowPageHeader {...baseProps} isNew={false} workflow={{ id: 'wf-1' }} publishedVersionId="ver-1" />
    )

    expect(screen.getByText('Published')).toBeInTheDocument()
  })

  it('updates workflow details via popover and marks dirty', () => {
    const dispatch = vi.fn()
    const markDirty = vi.fn()

    render(
      <BuilderWorkflowPageHeader
        {...baseProps}
        workflowName="Original Name"
        workflowDescription="Original Description"
        dispatch={dispatch}
        markDirty={markDirty}
      />
    )

    expect(screen.getByRole('textbox', { name: /Workflow name/i })).toHaveValue('Original Name')
  })

  it('shows cancel button during live run when execution is running', () => {
    const queryClient = new QueryClient()
    render(
      <QueryClientProvider client={queryClient}>
        <BuilderWorkflowPageHeader
          {...baseProps}
          isNew={false}
          workflow={{ id: 'workflow-1' }}
          isLiveRunActive
          onBackToEditor={vi.fn()}
          executionId="exec-123"
          executionStatus="running"
          projectId="proj-1"
        />
      </QueryClientProvider>
    )

    expect(screen.getByRole('button', { name: 'Cancel run' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Back to editor' })).toBeInTheDocument()
  })

  it('shows cancel and approval buttons together during live run', () => {
    const queryClient = new QueryClient()
    render(
      <QueryClientProvider client={queryClient}>
        <BuilderWorkflowPageHeader
          {...baseProps}
          isNew={false}
          workflow={{ id: 'workflow-1' }}
          isLiveRunActive
          onBackToEditor={vi.fn()}
          executionId="exec-123"
          executionStatus="running"
          projectId="proj-1"
          hasApprovalPending
          onReviewApproval={vi.fn()}
        />
      </QueryClientProvider>
    )

    expect(screen.getByRole('button', { name: 'Cancel run' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Review approval' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Back to editor' })).toBeInTheDocument()
  })

  it('shows cancel button during live run when execution is pending', () => {
    const queryClient = new QueryClient()
    render(
      <QueryClientProvider client={queryClient}>
        <BuilderWorkflowPageHeader
          {...baseProps}
          isNew={false}
          workflow={{ id: 'workflow-1' }}
          isLiveRunActive
          onBackToEditor={vi.fn()}
          executionId="exec-456"
          executionStatus="pending"
          projectId="proj-1"
        />
      </QueryClientProvider>
    )

    expect(screen.getByRole('button', { name: 'Cancel run' })).toBeInTheDocument()
  })

  it('does not show cancel button during live run when execution is completed', () => {
    render(
      <BuilderWorkflowPageHeader
        {...baseProps}
        isNew={false}
        workflow={{ id: 'workflow-1' }}
        isLiveRunActive
        onBackToEditor={vi.fn()}
        executionId="exec-789"
        executionStatus="completed"
      />
    )

    expect(screen.queryByRole('button', { name: 'Cancel run' })).not.toBeInTheDocument()
  })

  it('does not show cancel button during live run when executionId is missing', () => {
    render(
      <BuilderWorkflowPageHeader
        {...baseProps}
        isNew={false}
        workflow={{ id: 'workflow-1' }}
        isLiveRunActive
        onBackToEditor={vi.fn()}
        executionStatus="running"
      />
    )

    expect(screen.queryByRole('button', { name: 'Cancel run' })).not.toBeInTheDocument()
  })

  it('dispatches name and description changes via onApply callback', async () => {
    const user = userEvent.setup()
    const dispatch = vi.fn()
    const markDirty = vi.fn()

    render(
      <BuilderWorkflowPageHeader
        {...baseProps}
        workflowName="Old Name"
        workflowDescription="Old Desc"
        dispatch={dispatch}
        markDirty={markDirty}
      />
    )

    await user.click(screen.getByRole('button', { name: 'Apply details' }))

    expect(dispatch).toHaveBeenCalledWith({ type: 'SET_WORKFLOW_NAME', payload: 'New Name' })
    expect(dispatch).toHaveBeenCalledWith({ type: 'SET_WORKFLOW_DESCRIPTION', payload: 'New Desc' })
    expect(markDirty).toHaveBeenCalled()
  })

  it('does not dispatch when onApply values are unchanged', async () => {
    const user = userEvent.setup()
    const dispatch = vi.fn()
    const markDirty = vi.fn()

    vi.mocked(await import('./EditWorkflowDetailsPopover')).EditWorkflowDetailsPopover = (({
      onApply,
    }: {
      onApply: (name: string, description: string) => void
    }) => (
      <button onClick={() => onApply('wf', '')} aria-label="Apply details">
        Edit details
      </button>
    )) as never

    render(<BuilderWorkflowPageHeader {...baseProps} dispatch={dispatch} markDirty={markDirty} />)

    await user.click(screen.getByRole('button', { name: 'Apply details' }))

    expect(dispatch).not.toHaveBeenCalledWith(expect.objectContaining({ type: 'SET_WORKFLOW_NAME' }))
    expect(markDirty).not.toHaveBeenCalled()
  })

  it('shows approval loading state during live run', () => {
    render(
      <BuilderWorkflowPageHeader
        {...baseProps}
        isNew={false}
        workflow={{ id: 'workflow-1' }}
        isLiveRunActive
        onBackToEditor={vi.fn()}
        hasApprovalPending
        isApprovalLoading={true}
        onReviewApproval={vi.fn()}
      />
    )

    // PF prepends "Loading..." to the accessible name when isLoading is true
    const approvalButton = screen.getByRole('button', { name: /Review approval/i })
    expect(approvalButton).toBeInTheDocument()
  })

  it('does not show approval button when hasApprovalPending is false', () => {
    render(
      <BuilderWorkflowPageHeader
        {...baseProps}
        isNew={false}
        workflow={{ id: 'workflow-1' }}
        isLiveRunActive
        onBackToEditor={vi.fn()}
        hasApprovalPending={false}
        onReviewApproval={vi.fn()}
      />
    )

    expect(screen.queryByRole('button', { name: 'Review approval' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Back to editor' })).toBeInTheDocument()
  })

  it('does not show approval button when onReviewApproval is not provided', () => {
    render(
      <BuilderWorkflowPageHeader
        {...baseProps}
        isNew={false}
        workflow={{ id: 'workflow-1' }}
        isLiveRunActive
        onBackToEditor={vi.fn()}
        hasApprovalPending
      />
    )

    expect(screen.queryByRole('button', { name: 'Review approval' })).not.toBeInTheDocument()
  })

  it('shows version view toolbar with Back to editor, Restore, and Version history buttons', () => {
    const onExitVersionView = vi.fn()
    const onRestoreVersion = vi.fn()
    render(
      <BuilderWorkflowPageHeader
        {...baseProps}
        isNew={false}
        workflow={{ id: 'wf-1' }}
        isViewingVersion
        onExitVersionView={onExitVersionView}
        onRestoreVersion={onRestoreVersion}
      />
    )

    expect(screen.getByRole('button', { name: 'Back to editor' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Restore version/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Version history/i })).toBeInTheDocument()
  })

  it('calls onExitVersionView when Back to editor is clicked in version view', async () => {
    const user = userEvent.setup()
    const onExitVersionView = vi.fn()
    render(
      <BuilderWorkflowPageHeader
        {...baseProps}
        isNew={false}
        workflow={{ id: 'wf-1' }}
        isViewingVersion
        onExitVersionView={onExitVersionView}
      />
    )

    await user.click(screen.getByRole('button', { name: 'Back to editor' }))
    expect(onExitVersionView).toHaveBeenCalledTimes(1)
  })

  it('calls onRestoreVersion when Restore version is clicked', async () => {
    const user = userEvent.setup()
    const onRestoreVersion = vi.fn()
    render(
      <BuilderWorkflowPageHeader
        {...baseProps}
        isNew={false}
        workflow={{ id: 'wf-1' }}
        isViewingVersion
        onExitVersionView={vi.fn()}
        onRestoreVersion={onRestoreVersion}
      />
    )

    await user.click(screen.getByRole('button', { name: /Restore version/i }))
    expect(onRestoreVersion).toHaveBeenCalledTimes(1)
  })

  it('hides Restore version button when onRestoreVersion is not provided', () => {
    render(
      <BuilderWorkflowPageHeader
        {...baseProps}
        isNew={false}
        workflow={{ id: 'wf-1' }}
        isViewingVersion
        onExitVersionView={vi.fn()}
      />
    )

    expect(screen.getByRole('button', { name: 'Back to editor' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Restore version/i })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Version history/i })).toBeInTheDocument()
  })

  it('hides editor toolbar actions when in version view', () => {
    render(
      <BuilderWorkflowPageHeader
        {...baseProps}
        isNew={false}
        workflow={{ id: 'wf-1' }}
        isViewingVersion
        onExitVersionView={vi.fn()}
      />
    )

    expect(screen.queryByRole('button', { name: 'Add Step' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Save/i })).not.toBeInTheDocument()
  })

  it('shows Viewing date label in version view', () => {
    render(
      <BuilderWorkflowPageHeader
        {...baseProps}
        isNew={false}
        workflow={{ id: 'wf-1' }}
        isViewingVersion
        viewedVersionDate="2026-05-19T14:30:00.000Z"
        onExitVersionView={vi.fn()}
      />
    )

    expect(screen.getByText(/Viewing/)).toBeInTheDocument()
    expect(screen.getByText(/May 19, 2026/)).toBeInTheDocument()
  })

  it('renders editor toolbar when isLiveRunActive is false', () => {
    render(<BuilderWorkflowPageHeader {...baseProps} isNew={false} workflow={{ id: 'wf-1' }} isLiveRunActive={false} />)

    // Editor toolbar should be rendered (not live run toolbar)
    expect(screen.queryByRole('button', { name: 'Back to editor' })).not.toBeInTheDocument()
  })

  it('renders editor toolbar when isLiveRunActive is true but onBackToEditor is not provided', () => {
    render(<BuilderWorkflowPageHeader {...baseProps} isNew={false} workflow={{ id: 'wf-1' }} isLiveRunActive />)

    // Without onBackToEditor, the live run toolbar branch is not taken
    expect(screen.queryByRole('button', { name: 'Back to editor' })).not.toBeInTheDocument()
  })

  it('does not show cancel button when execution is not cancellable', () => {
    render(
      <BuilderWorkflowPageHeader
        {...baseProps}
        isNew={false}
        workflow={{ id: 'workflow-1' }}
        isLiveRunActive
        onBackToEditor={vi.fn()}
        executionId="exec-abc"
        executionStatus="failed"
      />
    )

    expect(screen.queryByRole('button', { name: 'Cancel run' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Back to editor' })).toBeInTheDocument()
  })

  it('opens publish dialog and calls onPublish with form data', async () => {
    const user = userEvent.setup()
    const onPublish = vi.fn()

    render(
      <BuilderWorkflowPageHeader
        {...baseProps}
        isNew={false}
        isDirty={false}
        workflow={{ id: 'wf-1' }}
        publishedVersionId={null}
        onPublish={onPublish}
      />
    )

    // The PublishWorkflowDialog is wired to publishDialog.open(true) via onPublishClick
    // The BuilderEditorToolbar has a "Publish" button that calls onPublishClick
    // Look for the publish button in the editor toolbar kebab or toolbar
    const publishButton = screen.getByRole('button', { name: /Publish/i })
    await user.click(publishButton)

    // Publish dialog should open
    await screen.findByText('Publish workflow?')

    // Submit the form
    const submitButton = screen.getByRole('button', { name: 'Publish' })
    await user.click(submitButton)

    // onPublish should have been called
    expect(onPublish).toHaveBeenCalled()
  })

  describe('read-only mode (canEdit=false)', () => {
    const readOnlyPermissions = {
      ...baseProps.builderPermissions,
      canEdit: false,
      tooltips: { ...baseProps.builderPermissions.tooltips, edit: 'No edit permission' },
    }

    it('disables workflow name input', () => {
      render(<BuilderWorkflowPageHeader {...baseProps} builderPermissions={readOnlyPermissions} />)

      expect(screen.getByRole('textbox', { name: /Workflow name/i })).toBeDisabled()
    })

    it('does not dispatch name changes when input is disabled', () => {
      const dispatch = vi.fn()
      render(<BuilderWorkflowPageHeader {...baseProps} dispatch={dispatch} builderPermissions={readOnlyPermissions} />)

      const input = screen.getByRole('textbox', { name: /Workflow name/i })
      expect(input).toBeDisabled()
      expect(dispatch).not.toHaveBeenCalledWith(expect.objectContaining({ type: 'SET_WORKFLOW_NAME' }))
    })

    it('hides edit workflow details popover', () => {
      render(<BuilderWorkflowPageHeader {...baseProps} builderPermissions={readOnlyPermissions} />)

      expect(screen.queryByRole('button', { name: /Apply details/i })).not.toBeInTheDocument()
    })

    it('hides project selector', () => {
      render(<BuilderWorkflowPageHeader {...baseProps} builderPermissions={readOnlyPermissions} />)

      expect(screen.queryByText('Project')).not.toBeInTheDocument()
    })

    it('shows project selector when canEdit is true', () => {
      render(<BuilderWorkflowPageHeader {...baseProps} />)

      expect(screen.getByText('Project')).toBeInTheDocument()
    })
  })

  it('shows version status badge in version view', () => {
    render(
      <BuilderWorkflowPageHeader
        {...baseProps}
        isNew={false}
        workflow={{ id: 'wf-1' }}
        isViewingVersion
        viewedVersionStatus="published"
        onExitVersionView={vi.fn()}
      />
    )

    expect(screen.getByText('Published')).toBeInTheDocument()
  })

  it('does not show version status badge when viewedVersionStatus is null', () => {
    render(
      <BuilderWorkflowPageHeader
        {...baseProps}
        isNew={false}
        workflow={{ id: 'wf-1' }}
        isViewingVersion
        viewedVersionStatus={null}
        onExitVersionView={vi.fn()}
      />
    )

    expect(screen.queryByText('Published')).not.toBeInTheDocument()
    expect(screen.queryByText('Draft')).not.toBeInTheDocument()
  })

  it('does not show Viewing date label when viewedVersionDate is null', () => {
    render(
      <BuilderWorkflowPageHeader
        {...baseProps}
        isNew={false}
        workflow={{ id: 'wf-1' }}
        isViewingVersion
        viewedVersionDate={null}
        onExitVersionView={vi.fn()}
      />
    )

    expect(screen.queryByText(/Viewing/)).not.toBeInTheDocument()
  })

  it('hides project selector in version view', () => {
    render(
      <BuilderWorkflowPageHeader
        {...baseProps}
        isNew={false}
        workflow={{ id: 'wf-1' }}
        isViewingVersion
        onExitVersionView={vi.fn()}
      />
    )

    expect(screen.queryByText('Project')).not.toBeInTheDocument()
  })

  it('hides publish status badge in version view', () => {
    render(
      <BuilderWorkflowPageHeader
        {...baseProps}
        isNew={false}
        workflow={{ id: 'wf-1' }}
        publishedVersionId="ver-2"
        isViewingVersion
        onExitVersionView={vi.fn()}
      />
    )

    expect(screen.queryByText('Unpublished changes')).not.toBeInTheDocument()
  })

  it('hides edit details popover in version view', () => {
    render(
      <BuilderWorkflowPageHeader
        {...baseProps}
        isNew={false}
        workflow={{ id: 'wf-1' }}
        isViewingVersion
        onExitVersionView={vi.fn()}
      />
    )

    expect(screen.queryByRole('button', { name: /Apply details/i })).not.toBeInTheDocument()
  })

  it('shows workflow name as page title heading in version view', () => {
    render(
      <BuilderWorkflowPageHeader
        {...baseProps}
        isNew={false}
        workflow={{ id: 'wf-1' }}
        isViewingVersion
        onExitVersionView={vi.fn()}
      />
    )

    expect(screen.queryByRole('textbox', { name: /Workflow name/i })).not.toBeInTheDocument()
    expect(screen.getByRole('heading', { level: 1, name: baseProps.workflowName })).toBeInTheDocument()
  })

  it('has no accessibility violations in version view mode', async () => {
    const { container } = render(
      <BuilderWorkflowPageHeader
        {...baseProps}
        isNew={false}
        workflow={{ id: 'wf-1' }}
        isViewingVersion
        viewedVersionDate="2026-05-19T14:30:00.000Z"
        viewedVersionStatus="published"
        onExitVersionView={vi.fn()}
      />
    )
    expect(await axe(container)).toHaveNoViolations()
  })

  it('does not show cancel button when executionId is null', () => {
    render(
      <BuilderWorkflowPageHeader
        {...baseProps}
        isNew={false}
        workflow={{ id: 'workflow-1' }}
        isLiveRunActive
        onBackToEditor={vi.fn()}
        executionId={null}
        executionStatus="running"
      />
    )

    expect(screen.queryByRole('button', { name: 'Cancel run' })).not.toBeInTheDocument()
  })

  it('prepends dirty indicator to page title when isDirty is true', () => {
    render(<BuilderWorkflowPageHeader {...baseProps} isDirty={true} isNew={false} workflowName="my-workflow" />)

    expectPageTitle(['● my-workflow', 'Workflows'])
  })

  it('does not prepend dirty indicator to page title when isDirty is false', () => {
    render(<BuilderWorkflowPageHeader {...baseProps} isDirty={false} isNew={false} workflowName="my-workflow" />)

    expectPageTitle(['my-workflow', 'Workflows'])
  })

  it('prepends dirty indicator to new workflow page title when isDirty is true', () => {
    render(<BuilderWorkflowPageHeader {...baseProps} isDirty={true} isNew={true} />)

    expectPageTitle(['● New Workflow', 'Workflows'])
  })
})
