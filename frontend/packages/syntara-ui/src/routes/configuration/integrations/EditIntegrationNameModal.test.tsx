import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { axe } from 'vitest-axe'

import { EditIntegrationNameModal } from './EditIntegrationNameModal'

const defaultProps = {
  isOpen: true,
  isSaving: false,
  initialName: 'ocp-us-east',
  onClose: vi.fn(),
  onSave: vi.fn(),
}

describe('EditIntegrationNameModal', () => {
  afterEach(() => {
    vi.clearAllMocks()
  })

  it('renders the title, helper copy, and pre-filled name', () => {
    render(<EditIntegrationNameModal {...defaultProps} />)

    expect(screen.getByText('Edit integration name')).toBeInTheDocument()
    expect(
      screen.getByText('You can only edit the server name / ID. All other settings are read-only.')
    ).toBeInTheDocument()
    expect(screen.getByRole('textbox', { name: /Server name \/ ID/i })).toHaveValue('ocp-us-east')
  })

  it('disables Save name when the value is unchanged', () => {
    render(<EditIntegrationNameModal {...defaultProps} />)

    expect(screen.getByRole('button', { name: 'Save name' })).toBeDisabled()
  })

  it('calls onSave with the new name when submitted', async () => {
    const user = userEvent.setup()
    render(<EditIntegrationNameModal {...defaultProps} />)

    const nameInput = screen.getByRole('textbox', { name: /Server name \/ ID/i })
    await user.clear(nameInput)
    await user.type(nameInput, 'renamed-cluster')
    await user.click(screen.getByRole('button', { name: 'Save name' }))

    expect(defaultProps.onSave).toHaveBeenCalledWith('renamed-cluster')
  })

  it('blocks submit and shows validation when the name is empty', async () => {
    const user = userEvent.setup()
    render(<EditIntegrationNameModal {...defaultProps} />)

    const nameInput = screen.getByRole('textbox', { name: /Server name \/ ID/i })
    await user.clear(nameInput)

    expect(screen.getByRole('button', { name: 'Save name' })).toBeDisabled()
    expect(defaultProps.onSave).not.toHaveBeenCalled()
  })

  it('calls onClose when Cancel is clicked', async () => {
    const user = userEvent.setup()
    render(<EditIntegrationNameModal {...defaultProps} />)

    await user.click(screen.getByRole('button', { name: 'Cancel' }))

    expect(defaultProps.onClose).toHaveBeenCalledTimes(1)
  })

  it('disables Cancel and shows loading Save name while saving', () => {
    render(<EditIntegrationNameModal {...defaultProps} isSaving />)

    expect(screen.getByRole('button', { name: 'Cancel' })).toBeDisabled()
  })

  it('does not render when isOpen is false', () => {
    render(<EditIntegrationNameModal {...defaultProps} isOpen={false} />)

    expect(screen.queryByText('Edit integration name')).not.toBeInTheDocument()
  })

  it('has no accessibility violations', async () => {
    const { container } = render(<EditIntegrationNameModal {...defaultProps} />)

    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })
})
