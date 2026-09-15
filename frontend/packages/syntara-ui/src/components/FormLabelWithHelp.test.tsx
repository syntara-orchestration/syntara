import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import { FormLabelWithHelp } from './FormLabelWithHelp'

describe('FormLabelWithHelp', () => {
  it('renders label without help control when helpText is omitted', () => {
    render(<FormLabelWithHelp label="Credential type" />)

    expect(screen.getByText('Credential type')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Credential type help' })).not.toBeInTheDocument()
  })

  it('opens help popover when helpText is provided', async () => {
    const user = userEvent.setup()

    render(<FormLabelWithHelp label="Credential type" helpText="Choose the credential type for this field." />)

    await user.click(screen.getByRole('button', { name: 'Credential type help' }))

    expect(screen.getByRole('dialog', { name: 'Credential type help' })).toBeInTheDocument()
    expect(screen.getByText('Choose the credential type for this field.')).toBeInTheDocument()
  })
})
