import { fireEvent, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { PermissionCheckNodeForm } from './PermissionCheckNodeForm'
import { renderWithHeader } from './test-utils/renderWithHeader'

describe('PermissionCheckNodeForm', () => {
  const mockOnSubmit = vi.fn()

  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders the activity name field', () => {
    renderWithHeader(<PermissionCheckNodeForm onSubmit={mockOnSubmit} />)

    expect(screen.getByPlaceholderText(/Enter activity name/i)).toBeInTheDocument()
  })

  it('explains that the step has no configuration', () => {
    renderWithHeader(<PermissionCheckNodeForm onSubmit={mockOnSubmit} />)

    expect(screen.getByText('This step has no configuration')).toBeInTheDocument()
    expect(screen.getByText(/single step connected to its input/i)).toBeInTheDocument()
  })

  it('documents the input and both output branches', () => {
    renderWithHeader(<PermissionCheckNodeForm onSubmit={mockOnSubmit} />)

    expect(screen.getByText('Input')).toBeInTheDocument()
    expect(screen.getByText('Allowed branch')).toBeInTheDocument()
    expect(screen.getByText('Denied branch')).toBeInTheDocument()
  })

  it('does not render a Settings tab', () => {
    renderWithHeader(<PermissionCheckNodeForm onSubmit={mockOnSubmit} />)

    expect(screen.queryByRole('tab', { name: 'Settings' })).not.toBeInTheDocument()
  })

  it('pre-populates the name from initialData', () => {
    renderWithHeader(<PermissionCheckNodeForm onSubmit={mockOnSubmit} initialData={{ name: 'Was it allowed' }} />)

    expect(screen.getByPlaceholderText(/Enter activity name/i)).toHaveValue('Was it allowed')
  })

  it('submits the edited name', async () => {
    const user = userEvent.setup()
    renderWithHeader(<PermissionCheckNodeForm onSubmit={mockOnSubmit} />)

    await user.type(screen.getByPlaceholderText(/Enter activity name/i), 'Check permission')
    fireEvent.submit(screen.getByTestId('permission-check-node-form'))

    await waitFor(() => {
      expect(mockOnSubmit).toHaveBeenCalledWith(
        expect.objectContaining({ name: 'Check permission' }),
        expect.anything()
      )
    })
  })

  it('has no accessibility violations', async () => {
    const { container } = renderWithHeader(<PermissionCheckNodeForm onSubmit={mockOnSubmit} />)

    const results = await axe(container, { rules: { 'aria-valid-attr-value': { enabled: false } } })

    expect(results).toHaveNoViolations()
  })
})
