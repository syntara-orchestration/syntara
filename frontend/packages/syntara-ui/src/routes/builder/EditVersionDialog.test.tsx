import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { axe } from 'vitest-axe'

import { EditVersionDialog } from './EditVersionDialog'

const defaultProps = {
  isOpen: true,
  isSaving: false,
  onClose: vi.fn(),
  onSave: vi.fn(),
  initialName: 'v1.0 release',
  initialDescription: 'Initial release',
}

describe('EditVersionDialog', () => {
  afterEach(() => {
    vi.clearAllMocks()
  })

  it('renders the dialog with title', () => {
    render(<EditVersionDialog {...defaultProps} />)

    expect(screen.getByText('Edit version name and description')).toBeInTheDocument()
  })

  it('pre-fills form with initial values', () => {
    render(<EditVersionDialog {...defaultProps} />)

    expect(screen.getByRole('textbox', { name: 'Version name' })).toHaveValue('v1.0 release')
    expect(screen.getByRole('textbox', { name: 'Description' })).toHaveValue('Initial release')
  })

  it('calls onSave with trimmed values on submit', async () => {
    const user = userEvent.setup()
    render(<EditVersionDialog {...defaultProps} />)

    const nameInput = screen.getByRole('textbox', { name: 'Version name' })
    await user.clear(nameInput)
    await user.type(nameInput, 'Updated name')
    await user.click(screen.getByRole('button', { name: 'Save version' }))

    expect(defaultProps.onSave).toHaveBeenCalledWith('Updated name', 'Initial release')
  })

  it('calls onSave with null when fields are empty', async () => {
    const user = userEvent.setup()
    render(<EditVersionDialog {...defaultProps} initialName="" initialDescription="" />)

    await user.click(screen.getByRole('button', { name: 'Save version' }))

    expect(defaultProps.onSave).toHaveBeenCalledWith(null, null)
  })

  it('calls onClose when Cancel is clicked', async () => {
    const user = userEvent.setup()
    render(<EditVersionDialog {...defaultProps} />)

    await user.click(screen.getByRole('button', { name: 'Cancel' }))

    expect(defaultProps.onClose).toHaveBeenCalledTimes(1)
  })

  it('disables buttons when isSaving is true', () => {
    render(<EditVersionDialog {...defaultProps} isSaving />)

    const buttons = screen.getAllByRole('button')
    const saveButton = buttons.find((b) => b.getAttribute('type') === 'submit')
    expect(saveButton).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeDisabled()
  })

  it('does not render when isOpen is false', () => {
    render(<EditVersionDialog {...defaultProps} isOpen={false} />)

    expect(screen.queryByText('Edit version name and description')).not.toBeInTheDocument()
  })

  it('calls onSave with trimmed whitespace-only values as null', async () => {
    const user = userEvent.setup()
    render(<EditVersionDialog {...defaultProps} initialName="   " initialDescription="   " />)

    await user.click(screen.getByRole('button', { name: 'Save version' }))

    expect(defaultProps.onSave).toHaveBeenCalledWith(null, null)
  })

  it('allows editing the description field', async () => {
    const user = userEvent.setup()
    render(<EditVersionDialog {...defaultProps} />)

    const descInput = screen.getByRole('textbox', { name: 'Description' })
    await user.clear(descInput)
    await user.type(descInput, 'Updated description')
    await user.click(screen.getByRole('button', { name: 'Save version' }))

    expect(defaultProps.onSave).toHaveBeenCalledWith('v1.0 release', 'Updated description')
  })

  it('pre-fills with null initial values as empty strings', () => {
    render(<EditVersionDialog {...defaultProps} initialName={undefined} initialDescription={undefined} />)

    expect(screen.getByRole('textbox', { name: 'Version name' })).toHaveValue('')
    expect(screen.getByRole('textbox', { name: 'Description' })).toHaveValue('')
  })

  it('shows validation error for publish name exceeding 255 characters', async () => {
    const user = userEvent.setup()
    render(<EditVersionDialog {...defaultProps} initialName="" />)

    const nameInput = screen.getByRole('textbox', { name: 'Version name' })
    await user.click(nameInput)
    await user.paste('x'.repeat(256))
    await user.click(screen.getByRole('button', { name: 'Save version' }))

    expect(defaultProps.onSave).not.toHaveBeenCalled()
    expect(screen.getByText(/255 character/i)).toBeInTheDocument()
  })

  it('has no accessibility violations', async () => {
    const { container } = render(<EditVersionDialog {...defaultProps} />)

    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })
})
