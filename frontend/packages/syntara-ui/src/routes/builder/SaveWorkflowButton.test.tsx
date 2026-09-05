import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { SaveWorkflowButton } from './SaveWorkflowButton'

const defaultProps = {
  isPending: false,
  isDirty: true,
  isNew: false,
  lastSavedAt: null,
  onSave: vi.fn(),
  canEdit: true,
  editTooltip: 'You need workflow:update permission',
}

describe('SaveWorkflowButton', () => {
  it('renders Save workflow with a save icon', () => {
    render(<SaveWorkflowButton {...defaultProps} />)
    const button = screen.getByRole('button', { name: /save workflow/i })
    expect(button).toBeInTheDocument()
    expect(within(button).getByRole('img', { hidden: true })).toBeInTheDocument()
  })

  it('shows Saving... when isPending', () => {
    render(<SaveWorkflowButton {...defaultProps} isPending={true} />)
    expect(screen.getByText('Saving...')).toBeInTheDocument()
  })

  it('is aria-disabled when isPending', () => {
    render(<SaveWorkflowButton {...defaultProps} isPending={true} />)
    expect(screen.getByRole('button', { name: /saving/i })).toHaveAttribute('aria-disabled', 'true')
  })

  it('is aria-disabled when not dirty and not new', () => {
    render(<SaveWorkflowButton {...defaultProps} isDirty={false} isNew={false} />)
    expect(screen.getByRole('button', { name: /save/i })).toHaveAttribute('aria-disabled', 'true')
  })

  it('is not aria-disabled when isDirty is true', () => {
    render(<SaveWorkflowButton {...defaultProps} isDirty={true} />)
    const button = screen.getByRole('button', { name: /save/i })
    expect(button).not.toHaveAttribute('aria-disabled', 'true')
  })

  it('is not aria-disabled when isNew is true even if not dirty', () => {
    render(<SaveWorkflowButton {...defaultProps} isDirty={false} isNew={true} />)
    const button = screen.getByRole('button', { name: /save/i })
    expect(button).not.toHaveAttribute('aria-disabled', 'true')
  })

  it('calls onSave when clicked and canEdit is true', async () => {
    const onSave = vi.fn()
    render(<SaveWorkflowButton {...defaultProps} onSave={onSave} />)
    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: /save/i }))
    expect(onSave).toHaveBeenCalledOnce()
  })

  it('does not call onSave when canEdit is false', async () => {
    const onSave = vi.fn()
    render(<SaveWorkflowButton {...defaultProps} onSave={onSave} canEdit={false} />)
    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: /save/i }))
    expect(onSave).not.toHaveBeenCalled()
  })

  it('is aria-disabled when canEdit is false', () => {
    render(<SaveWorkflowButton {...defaultProps} canEdit={false} />)
    expect(screen.getByRole('button', { name: /save/i })).toHaveAttribute('aria-disabled', 'true')
  })

  it('has no accessibility violations', async () => {
    const { container } = render(<SaveWorkflowButton {...defaultProps} />)
    expect(await axe(container)).toHaveNoViolations()
  })

  it('is aria-disabled when isNodeEditorOpen is true', () => {
    render(<SaveWorkflowButton {...defaultProps} isNodeEditorOpen={true} />)
    expect(screen.getByRole('button', { name: /save/i })).toHaveAttribute('aria-disabled', 'true')
  })

  it('does not call onSave when isNodeEditorOpen is true', async () => {
    const onSave = vi.fn()
    render(<SaveWorkflowButton {...defaultProps} onSave={onSave} isNodeEditorOpen={true} />)
    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: /save/i }))
    expect(onSave).not.toHaveBeenCalled()
  })

  it('shows "finish editing" tooltip when isNodeEditorOpen is true', async () => {
    render(<SaveWorkflowButton {...defaultProps} isNodeEditorOpen={true} />)
    const user = userEvent.setup()
    await user.hover(screen.getByRole('button', { name: /save/i }))
    expect(await screen.findByText(/Finish editing the current step before saving/)).toBeInTheDocument()
  })

  it('has no accessibility violations when disabled', async () => {
    const { container } = render(<SaveWorkflowButton {...defaultProps} canEdit={false} />)
    expect(await axe(container)).toHaveNoViolations()
  })
})
