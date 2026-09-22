import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { ImportConfirmationDialog } from './ImportConfirmationDialog'

function renderDialog(overrides: Partial<React.ComponentProps<typeof ImportConfirmationDialog>> = {}) {
  const props: React.ComponentProps<typeof ImportConfirmationDialog> = {
    isOpen: true,
    onClose: vi.fn(),
    onImportCurrent: vi.fn(),
    onImportNew: vi.fn(),
    workflowName: 'My Workflow',
    isDirty: false,
    isPending: false,
    ...overrides,
  }
  return { ...render(<ImportConfirmationDialog {...props} />), props }
}

describe('ImportConfirmationDialog', () => {
  it('renders title and body text with workflow name', () => {
    renderDialog()

    expect(screen.getByText('Import workflow?')).toBeInTheDocument()
    expect(screen.getByText(/My Workflow/)).toBeInTheDocument()
  })

  it('renders two radio options and Import/Cancel buttons', () => {
    renderDialog()

    expect(screen.getByRole('radio', { name: /Import as new workflow/ })).toBeInTheDocument()
    expect(screen.getByRole('radio', { name: /Import into current workflow/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Import workflow' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeInTheDocument()
  })

  it('defaults to "Import as new workflow" selected', () => {
    renderDialog()

    expect(screen.getByRole('radio', { name: /Import as new workflow/ })).toBeChecked()
    expect(screen.getByRole('radio', { name: /Import into current workflow/ })).not.toBeChecked()
  })

  it('calls onImportNew when Import is clicked with default selection', async () => {
    const user = userEvent.setup()
    const { props } = renderDialog()

    await user.click(screen.getByRole('button', { name: 'Import workflow' }))

    expect(props.onImportNew).toHaveBeenCalledOnce()
    expect(props.onImportCurrent).not.toHaveBeenCalled()
  })

  it('calls onImportCurrent when "Import into current workflow" is selected and Import is clicked', async () => {
    const user = userEvent.setup()
    const { props } = renderDialog()

    await user.click(screen.getByRole('radio', { name: /Import into current workflow/ }))
    await user.click(screen.getByRole('button', { name: 'Import workflow' }))

    expect(props.onImportCurrent).toHaveBeenCalledOnce()
    expect(props.onImportNew).not.toHaveBeenCalled()
  })

  it('calls onClose when Cancel is clicked', async () => {
    const user = userEvent.setup()
    const { props } = renderDialog()

    await user.click(screen.getByRole('button', { name: 'Cancel' }))

    expect(props.onClose).toHaveBeenCalledOnce()
  })

  it('does not render when isOpen is false', () => {
    renderDialog({ isOpen: false })

    expect(screen.queryByText('Import workflow?')).not.toBeInTheDocument()
  })

  it('shows unsaved changes warning when isDirty is true', () => {
    renderDialog({ isDirty: true })

    expect(screen.getByText(/You have unsaved changes that will be lost/)).toBeInTheDocument()
  })

  it('does not show unsaved changes warning when isDirty is false', () => {
    renderDialog({ isDirty: false })

    expect(screen.queryByText(/You have unsaved changes that will be lost/)).not.toBeInTheDocument()
  })

  it('handles empty workflow name gracefully', () => {
    renderDialog({ workflowName: '' })

    expect(screen.getByText('Choose how to import:')).toBeInTheDocument()
  })

  it('disables buttons when isPending is true', () => {
    renderDialog({ isPending: true })

    expect(screen.getByRole('button', { name: /Import/ })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeDisabled()
  })

  it('has no accessibility violations', async () => {
    const { container } = renderDialog()

    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })
})
