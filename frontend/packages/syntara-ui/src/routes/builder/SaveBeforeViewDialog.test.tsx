import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { SaveBeforeViewDialog } from './SaveBeforeViewDialog'

const defaultProps = {
  isOpen: true,
  onSave: vi.fn().mockResolvedValue(true),
  onViewWithoutSaving: vi.fn(),
  onCancel: vi.fn(),
}

describe('SaveBeforeViewDialog', () => {
  afterEach(() => {
    vi.clearAllMocks()
  })

  it('renders the dialog with title and body when open', () => {
    render(<SaveBeforeViewDialog {...defaultProps} />)

    expect(screen.getByText('Save changes before viewing this version?')).toBeInTheDocument()
    expect(screen.getByText(/permanently delete all recent unsaved progress/)).toBeInTheDocument()
  })

  it('does not render when isOpen is false', () => {
    render(<SaveBeforeViewDialog {...defaultProps} isOpen={false} />)

    expect(screen.queryByText('Save changes before viewing this version?')).not.toBeInTheDocument()
  })

  it('renders three action buttons', () => {
    render(<SaveBeforeViewDialog {...defaultProps} />)

    expect(screen.getByRole('button', { name: 'Save workflow' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'View version without saving' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeInTheDocument()
  })

  it('calls onSave when Save workflow is clicked', async () => {
    const user = userEvent.setup()
    const onSave = vi.fn().mockResolvedValue(true)
    render(<SaveBeforeViewDialog {...defaultProps} onSave={onSave} />)

    await user.click(screen.getByRole('button', { name: 'Save workflow' }))

    expect(onSave).toHaveBeenCalledTimes(1)
  })

  it('calls onViewWithoutSaving when View version without saving is clicked', async () => {
    const user = userEvent.setup()
    const onViewWithoutSaving = vi.fn()
    render(<SaveBeforeViewDialog {...defaultProps} onViewWithoutSaving={onViewWithoutSaving} />)

    await user.click(screen.getByRole('button', { name: 'View version without saving' }))

    expect(onViewWithoutSaving).toHaveBeenCalledTimes(1)
  })

  it('calls onCancel when Cancel is clicked', async () => {
    const user = userEvent.setup()
    const onCancel = vi.fn()
    render(<SaveBeforeViewDialog {...defaultProps} onCancel={onCancel} />)

    await user.click(screen.getByRole('button', { name: 'Cancel' }))

    expect(onCancel).toHaveBeenCalledTimes(1)
  })

  it('renders custom title when provided', () => {
    const customTitle = 'Save changes before opening the duplicate?'
    render(<SaveBeforeViewDialog {...defaultProps} title={customTitle} />)

    expect(screen.getByText(customTitle)).toBeInTheDocument()
  })

  it('renders custom body text when provided', () => {
    const customBodyText = 'Custom save prompt message'
    render(<SaveBeforeViewDialog {...defaultProps} bodyText={customBodyText} />)

    expect(screen.getByText(customBodyText)).toBeInTheDocument()
  })

  it('renders custom button label when provided', () => {
    const customButtonLabel = 'Open without saving'
    render(<SaveBeforeViewDialog {...defaultProps} buttonLabel={customButtonLabel} />)

    expect(screen.getByRole('button', { name: customButtonLabel })).toBeInTheDocument()
  })

  describe('accessibility', () => {
    it('has no violations when open', async () => {
      const { container } = render(<SaveBeforeViewDialog {...defaultProps} />)
      expect(await axe(container)).toHaveNoViolations()
    })
  })
})
