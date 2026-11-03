import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { RunWorkflowSection } from './RunWorkflowSection'
import { workflowVerificationBlockedTooltip } from './workflowVerificationBlockedTooltip'

describe('RunWorkflowSection', () => {
  const defaultPermissions = {
    canEdit: true,
    canCreate: true,
    canRun: true,
    canDelete: true,
    isLoading: false,
    tooltips: { edit: '', save: '', publish: '', unpublish: '', run: 'No run permission', delete: '', create: '' },
  }

  const defaultProps = {
    isSaved: true,
    validationErrorCount: 0,
    triggers: [{ id: 'trigger-1', name: 'Manual' }],
    dispatch: vi.fn(),
    builderPermissions: defaultPermissions,
  }

  afterEach(() => {
    vi.clearAllMocks()
  })

  describe('tooltip priority', () => {
    it('shows permission tooltip when canRun is false and no triggers', async () => {
      const user = userEvent.setup()
      render(
        <RunWorkflowSection
          {...defaultProps}
          triggers={undefined}
          builderPermissions={{ ...defaultPermissions, canRun: false }}
        />
      )

      await user.hover(screen.getByRole('button', { name: /^Run$/i }))

      expect(await screen.findByText('No run permission')).toBeInTheDocument()
    })

    it('shows node-editor tooltip when isNodeEditorOpen is true', async () => {
      const user = userEvent.setup()
      render(<RunWorkflowSection {...defaultProps} isNodeEditorOpen />)

      await user.hover(screen.getByRole('button', { name: /^Run$/i }))

      expect(await screen.findByText('Finish editing the current step before running')).toBeInTheDocument()
    })

    it('shows permission tooltip over node-editor when canRun is false and editor is open', async () => {
      const user = userEvent.setup()
      render(
        <RunWorkflowSection
          {...defaultProps}
          isNodeEditorOpen
          builderPermissions={{ ...defaultPermissions, canRun: false }}
        />
      )

      await user.hover(screen.getByRole('button', { name: /^Run$/i }))

      expect(await screen.findByText('No run permission')).toBeInTheDocument()
    })

    it('shows node-editor tooltip over save-first when both editor open and unsaved', async () => {
      const user = userEvent.setup()
      render(<RunWorkflowSection {...defaultProps} isSaved={false} isNodeEditorOpen />)

      await user.hover(screen.getByRole('button', { name: /^Run$/i }))

      expect(await screen.findByText('Finish editing the current step before running')).toBeInTheDocument()
    })

    it('shows save-first tooltip when workflow is unsaved with triggers', async () => {
      const user = userEvent.setup()
      render(<RunWorkflowSection {...defaultProps} isSaved={false} />)

      await user.hover(screen.getByRole('button', { name: /^Run$/i }))

      expect(await screen.findByText('Save workflow before running')).toBeInTheDocument()
    })

    it('shows no-triggers tooltip when saved but no triggers', async () => {
      const user = userEvent.setup()
      render(<RunWorkflowSection {...defaultProps} triggers={undefined} />)

      await user.hover(screen.getByRole('button', { name: /^Run$/i }))

      expect(
        await screen.findByText('At least one trigger step needs to be placed on the canvas for this workflow to run')
      ).toBeInTheDocument()
    })

    it('shows save-first tooltip over no-triggers when both unsaved and no triggers', async () => {
      const user = userEvent.setup()
      render(<RunWorkflowSection {...defaultProps} isSaved={false} triggers={undefined} />)

      await user.hover(screen.getByRole('button', { name: /^Run$/i }))

      expect(await screen.findByText('Save workflow before running')).toBeInTheDocument()
    })

    it('shows permission tooltip over save-first when both canRun is false and unsaved', async () => {
      const user = userEvent.setup()
      render(
        <RunWorkflowSection
          {...defaultProps}
          isSaved={false}
          builderPermissions={{ ...defaultPermissions, canRun: false }}
        />
      )

      await user.hover(screen.getByRole('button', { name: /^Run$/i }))

      expect(await screen.findByText('No run permission')).toBeInTheDocument()
    })

    it('shows validation tooltip when saved with a single validation issue', async () => {
      const user = userEvent.setup()
      render(<RunWorkflowSection {...defaultProps} validationErrorCount={1} />)

      await user.hover(screen.getByRole('button', { name: /^Run$/i }))

      expect(await screen.findByText(workflowVerificationBlockedTooltip('running', 1))).toBeInTheDocument()
    })

    it('shows validation tooltip when banner count blocks run even if store count is zero', async () => {
      const user = userEvent.setup()
      render(<RunWorkflowSection {...defaultProps} bannerBlockingValidationErrorCount={2} />)

      await user.hover(screen.getByRole('button', { name: /^Run$/i }))

      expect(await screen.findByText(workflowVerificationBlockedTooltip('running', 2))).toBeInTheDocument()
    })

    it('shows plural validation tooltip when multiple issues are recorded', async () => {
      const user = userEvent.setup()
      render(<RunWorkflowSection {...defaultProps} validationErrorCount={3} />)

      await user.hover(screen.getByRole('button', { name: /^Run$/i }))

      expect(await screen.findByText(workflowVerificationBlockedTooltip('running', 3))).toBeInTheDocument()
    })

    it('shows no-triggers tooltip over validation issues when both apply', async () => {
      const user = userEvent.setup()
      render(<RunWorkflowSection {...defaultProps} triggers={undefined} validationErrorCount={2} />)

      await user.hover(screen.getByRole('button', { name: /^Run$/i }))

      expect(
        await screen.findByText('At least one trigger step needs to be placed on the canvas for this workflow to run')
      ).toBeInTheDocument()
    })
  })

  describe('disabled state', () => {
    it('is enabled when saved, has triggers, and canRun', () => {
      render(<RunWorkflowSection {...defaultProps} />)

      expect(screen.getByRole('button', { name: /^Run$/i })).not.toHaveAttribute('aria-disabled', 'true')
    })

    it('is disabled when canRun is false', () => {
      render(<RunWorkflowSection {...defaultProps} builderPermissions={{ ...defaultPermissions, canRun: false }} />)

      expect(screen.getByRole('button', { name: /^Run$/i })).toHaveAttribute('aria-disabled', 'true')
    })

    it('is disabled when not saved', () => {
      render(<RunWorkflowSection {...defaultProps} isSaved={false} />)

      expect(screen.getByRole('button', { name: /^Run$/i })).toHaveAttribute('aria-disabled', 'true')
    })

    it('is disabled when no triggers', () => {
      render(<RunWorkflowSection {...defaultProps} triggers={undefined} />)

      expect(screen.getByRole('button', { name: /^Run$/i })).toHaveAttribute('aria-disabled', 'true')
    })

    it('is disabled when isNodeEditorOpen is true', () => {
      render(<RunWorkflowSection {...defaultProps} isNodeEditorOpen />)

      expect(screen.getByRole('button', { name: /^Run$/i })).toHaveAttribute('aria-disabled', 'true')
    })

    it('is disabled when saved but validationErrorCount is greater than zero', () => {
      render(<RunWorkflowSection {...defaultProps} validationErrorCount={1} />)

      expect(screen.getByRole('button', { name: /^Run$/i })).toHaveAttribute('aria-disabled', 'true')
    })

    it('disables the multi-trigger toggle when validationErrorCount is greater than zero', () => {
      render(
        <RunWorkflowSection
          {...defaultProps}
          validationErrorCount={1}
          triggers={[
            { id: 'trigger-1', name: 'Manual' },
            { id: 'trigger-2', name: 'Webhook' },
          ]}
        />
      )

      const runToggle = screen.getByRole('button', { name: /Run workflow/i })
      expect(runToggle).toHaveAttribute('aria-disabled', 'true')
      expect(runToggle).not.toBeDisabled()
    })

    it('shows validation tooltip on focus for multi-trigger Run when blocked', async () => {
      const user = userEvent.setup()
      render(
        <RunWorkflowSection
          {...defaultProps}
          validationErrorCount={1}
          triggers={[
            { id: 'trigger-1', name: 'Manual' },
            { id: 'trigger-2', name: 'Webhook' },
          ]}
        />
      )

      await user.tab()
      expect(await screen.findByText(workflowVerificationBlockedTooltip('running', 1))).toBeInTheDocument()
    })
  })

  describe('click behavior', () => {
    it('dispatches SET_CONFIRM_DIALOG when enabled and clicked', async () => {
      const user = userEvent.setup()
      const dispatch = vi.fn()
      render(<RunWorkflowSection {...defaultProps} dispatch={dispatch} />)

      await user.click(screen.getByRole('button', { name: /^Run$/i }))

      expect(dispatch).toHaveBeenCalledWith({ type: 'SET_CONFIRM_DIALOG', payload: true })
    })

    it('does not dispatch when disabled and clicked', async () => {
      const user = userEvent.setup()
      const dispatch = vi.fn()
      render(<RunWorkflowSection {...defaultProps} isSaved={false} dispatch={dispatch} />)

      await user.click(screen.getByRole('button', { name: /^Run$/i }))

      expect(dispatch).not.toHaveBeenCalled()
    })

    it('does not dispatch when there are validation issues and clicked', async () => {
      const user = userEvent.setup()
      const dispatch = vi.fn()
      render(<RunWorkflowSection {...defaultProps} validationErrorCount={1} dispatch={dispatch} />)

      await user.click(screen.getByRole('button', { name: /^Run$/i }))

      expect(dispatch).not.toHaveBeenCalled()
    })

    it('keeps Run focusable and shows validation tooltip when issues are recorded', async () => {
      const user = userEvent.setup()
      const dispatch = vi.fn()
      render(<RunWorkflowSection {...defaultProps} validationErrorCount={2} dispatch={dispatch} />)

      const runButton = screen.getByRole('button', { name: /^Run$/i })
      expect(runButton).toHaveAttribute('aria-disabled', 'true')
      expect(runButton).not.toBeDisabled()

      await user.hover(runButton)
      expect(await screen.findByText(workflowVerificationBlockedTooltip('running', 2))).toBeInTheDocument()

      await user.click(runButton)
      expect(dispatch).not.toHaveBeenCalled()
    })
  })

  describe('accessibility', () => {
    it('has no violations when enabled', async () => {
      const { container } = render(<RunWorkflowSection {...defaultProps} />)

      expect(await axe(container)).toHaveNoViolations()
    })

    it('has no violations when disabled', async () => {
      const { container } = render(<RunWorkflowSection {...defaultProps} isSaved={false} triggers={undefined} />)

      expect(await axe(container)).toHaveNoViolations()
    })
  })
})
