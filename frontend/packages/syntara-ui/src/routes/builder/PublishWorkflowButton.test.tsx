import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { axe } from 'vitest-axe'

import { PublishWorkflowButton } from './PublishWorkflowButton'

const defaultProps = {
  canEdit: true,
  hasNoSteps: false,
  hasNoChanges: false,
  validationErrorCount: 0,
  isVerifying: false,
  editTooltip: 'You need edit permission',
  handleVerify: vi.fn(),
  onPublishClick: vi.fn(),
}

describe('PublishWorkflowButton', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders the Publish workflow button', () => {
    render(<PublishWorkflowButton {...defaultProps} />)

    expect(screen.getByRole('button', { name: /Publish workflow/i })).toBeInTheDocument()
  })

  it('button is enabled when canEdit is true, no errors, and not verifying', () => {
    render(<PublishWorkflowButton {...defaultProps} />)

    expect(screen.getByRole('button', { name: /Publish workflow/i })).not.toHaveAttribute('aria-disabled', 'true')
  })

  it('button is aria-disabled when canEdit is false', () => {
    render(<PublishWorkflowButton {...defaultProps} canEdit={false} />)

    expect(screen.getByRole('button', { name: /Publish workflow/i })).toHaveAttribute('aria-disabled', 'true')
  })

  it('button is aria-disabled when validationErrorCount is greater than zero', () => {
    render(<PublishWorkflowButton {...defaultProps} validationErrorCount={3} />)

    expect(screen.getByRole('button', { name: /Publish workflow/i })).toHaveAttribute('aria-disabled', 'true')
  })

  it('button is aria-disabled when isVerifying is true', () => {
    render(<PublishWorkflowButton {...defaultProps} isVerifying />)

    expect(screen.getByRole('button', { name: /Publish workflow/i })).toHaveAttribute('aria-disabled', 'true')
  })

  it('shows verifying tooltip when isVerifying is true', async () => {
    const user = userEvent.setup()

    render(<PublishWorkflowButton {...defaultProps} isVerifying />)

    await user.hover(screen.getByRole('button', { name: /Publish workflow/i }))

    expect(await screen.findByText('Verifying workflow...')).toBeInTheDocument()
  })

  it('shows singular error text when validationErrorCount is 1', async () => {
    const user = userEvent.setup()

    render(<PublishWorkflowButton {...defaultProps} validationErrorCount={1} />)

    await user.hover(screen.getByRole('button', { name: /Publish workflow/i }))

    expect(await screen.findByText('Verify your workflow before publishing — 1 error found')).toBeInTheDocument()
  })

  it('shows plural errors text when validationErrorCount is greater than 1', async () => {
    const user = userEvent.setup()

    render(<PublishWorkflowButton {...defaultProps} validationErrorCount={5} />)

    await user.hover(screen.getByRole('button', { name: /Publish workflow/i }))

    expect(await screen.findByText('Verify your workflow before publishing — 5 errors found')).toBeInTheDocument()
  })

  it('shows editTooltip when canEdit is false', async () => {
    const user = userEvent.setup()

    render(<PublishWorkflowButton {...defaultProps} canEdit={false} editTooltip="No publish permission" />)

    await user.hover(screen.getByRole('button', { name: /Publish workflow/i }))

    expect(await screen.findByText('No publish permission')).toBeInTheDocument()
  })

  it('calls handleVerify with a callback when clicked and button is enabled', async () => {
    const user = userEvent.setup()
    const handleVerify = vi.fn()

    render(<PublishWorkflowButton {...defaultProps} handleVerify={handleVerify} />)

    await user.click(screen.getByRole('button', { name: /Publish workflow/i }))

    expect(handleVerify).toHaveBeenCalledTimes(1)
    expect(handleVerify).toHaveBeenCalledWith(expect.any(Function))
  })

  it('handleVerify callback invokes onPublishClick', async () => {
    const user = userEvent.setup()
    const onPublishClick = vi.fn()
    const handleVerify = vi.fn((cb?: () => void) => cb?.())

    render(<PublishWorkflowButton {...defaultProps} handleVerify={handleVerify} onPublishClick={onPublishClick} />)

    await user.click(screen.getByRole('button', { name: /Publish workflow/i }))

    expect(onPublishClick).toHaveBeenCalledTimes(1)
  })

  it('does not call handleVerify when validationErrorCount is greater than zero', async () => {
    const user = userEvent.setup()
    const handleVerify = vi.fn()

    render(<PublishWorkflowButton {...defaultProps} handleVerify={handleVerify} validationErrorCount={2} />)

    await user.click(screen.getByRole('button', { name: /Publish workflow/i }))

    expect(handleVerify).not.toHaveBeenCalled()
  })

  it('does not call handleVerify when canEdit is false', async () => {
    const user = userEvent.setup()
    const handleVerify = vi.fn()

    render(<PublishWorkflowButton {...defaultProps} handleVerify={handleVerify} canEdit={false} />)

    await user.click(screen.getByRole('button', { name: /Publish workflow/i }))

    expect(handleVerify).not.toHaveBeenCalled()
  })

  it('button is aria-disabled when hasNoChanges is true', () => {
    render(<PublishWorkflowButton {...defaultProps} hasNoChanges />)

    expect(screen.getByRole('button', { name: /Publish workflow/i })).toHaveAttribute('aria-disabled', 'true')
  })

  it('shows no-changes tooltip when hasNoChanges is true', async () => {
    const user = userEvent.setup()

    render(<PublishWorkflowButton {...defaultProps} hasNoChanges />)

    await user.hover(screen.getByRole('button', { name: /Publish workflow/i }))

    expect(await screen.findByText('No changes to publish')).toBeInTheDocument()
  })

  it('does not call handleVerify when hasNoChanges is true', async () => {
    const user = userEvent.setup()
    const handleVerify = vi.fn()

    render(<PublishWorkflowButton {...defaultProps} handleVerify={handleVerify} hasNoChanges />)

    await user.click(screen.getByRole('button', { name: /Publish workflow/i }))

    expect(handleVerify).not.toHaveBeenCalled()
  })

  it('button is aria-disabled when hasNoSteps is true', () => {
    render(<PublishWorkflowButton {...defaultProps} hasNoSteps />)

    expect(screen.getByRole('button', { name: /Publish workflow/i })).toHaveAttribute('aria-disabled', 'true')
  })

  it('shows no-steps tooltip when hasNoSteps is true', async () => {
    const user = userEvent.setup()

    render(<PublishWorkflowButton {...defaultProps} hasNoSteps />)

    await user.hover(screen.getByRole('button', { name: /Publish workflow/i }))

    expect(await screen.findByText('Complete your workflow before publishing')).toBeInTheDocument()
  })

  it('does not call handleVerify when hasNoSteps is true', async () => {
    const user = userEvent.setup()
    const handleVerify = vi.fn()

    render(<PublishWorkflowButton {...defaultProps} handleVerify={handleVerify} hasNoSteps />)

    await user.click(screen.getByRole('button', { name: /Publish workflow/i }))

    expect(handleVerify).not.toHaveBeenCalled()
  })

  it('has no accessibility violations when enabled', async () => {
    const { container } = render(<PublishWorkflowButton {...defaultProps} />)

    expect(await axe(container)).toHaveNoViolations()
  })

  it('button is aria-disabled when isStepEditorOpen is true', () => {
    render(<PublishWorkflowButton {...defaultProps} isStepEditorOpen={true} />)

    expect(screen.getByRole('button', { name: /Publish workflow/i })).toHaveAttribute('aria-disabled', 'true')
  })

  it('shows "finish editing" tooltip when isStepEditorOpen is true', async () => {
    const user = userEvent.setup()

    render(<PublishWorkflowButton {...defaultProps} isStepEditorOpen={true} />)

    await user.hover(screen.getByRole('button', { name: /Publish workflow/i }))

    expect(await screen.findByText('Finish editing the current step before publishing')).toBeInTheDocument()
  })

  it('does not call handleVerify when isStepEditorOpen is true', async () => {
    const user = userEvent.setup()
    const handleVerify = vi.fn()

    render(<PublishWorkflowButton {...defaultProps} handleVerify={handleVerify} isStepEditorOpen={true} />)

    await user.click(screen.getByRole('button', { name: /Publish workflow/i }))

    expect(handleVerify).not.toHaveBeenCalled()
  })

  it('shows permission tooltip over node-editor tooltip when canEdit is false', async () => {
    const user = userEvent.setup()

    render(<PublishWorkflowButton {...defaultProps} canEdit={false} isStepEditorOpen={true} />)

    await user.hover(screen.getByRole('button', { name: /Publish workflow/i }))

    expect(await screen.findByText('You need edit permission')).toBeInTheDocument()
  })

  it('has no accessibility violations when disabled', async () => {
    const { container } = render(<PublishWorkflowButton {...defaultProps} canEdit={false} />)

    expect(await axe(container)).toHaveNoViolations()
  })
})
