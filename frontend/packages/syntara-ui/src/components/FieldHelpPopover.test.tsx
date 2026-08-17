import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { axe } from 'vitest-axe'

import { createFieldHelp } from './createFieldHelp'
import { FieldHelpPopover } from './FieldHelpPopover'

describe('FieldHelpPopover', () => {
  it('opens popover body when help control is activated', async () => {
    const user = userEvent.setup()
    render(<FieldHelpPopover helpText="Explanation for this field." />)
    await user.click(screen.getByRole('button', { name: 'More info' }))
    expect(screen.getByRole('dialog', { name: 'Field help' })).toBeInTheDocument()
    expect(screen.getByText('Explanation for this field.')).toBeInTheDocument()
  })

  it('uses headerContent in the trigger accessible name', async () => {
    const user = userEvent.setup()
    render(<FieldHelpPopover headerContent="Input schema" helpText="Define an input schema." />)
    await user.click(screen.getByRole('button', { name: 'More info for Input schema' }))
    expect(screen.getByText('Input schema')).toBeInTheDocument()
    expect(screen.getByText('Define an input schema.')).toBeInTheDocument()
  })

  it('supports ReactNode body content', async () => {
    const user = userEvent.setup()
    render(
      <FieldHelpPopover
        helpText={
          <span>
            First sentence. <strong>Important note.</strong>
          </span>
        }
      />
    )
    await user.click(screen.getByRole('button', { name: 'More info' }))
    expect(screen.getByText('Important note.')).toBeInTheDocument()
  })

  it('uses generic More info label when headerContent is not a string', async () => {
    const user = userEvent.setup()
    render(<FieldHelpPopover headerContent={<span>Custom header</span>} helpText="Body copy." />)
    await user.click(screen.getByRole('button', { name: 'More info' }))
    expect(screen.getByText('Custom header')).toBeInTheDocument()
    expect(screen.getByText('Body copy.')).toBeInTheDocument()
  })

  it('uses a custom aria-label on the popover when provided', async () => {
    const user = userEvent.setup()
    render(
      <FieldHelpPopover
        helpText="Issuer URL help body."
        headerContent="Issuer URL"
        aria-label="Issuer URL field help"
      />
    )

    await user.click(screen.getByRole('button', { name: 'More info for Issuer URL' }))

    expect(screen.getByText('Issuer URL help body.')).toBeInTheDocument()
  })

  it('has no accessibility violations', async () => {
    const { container } = render(<FieldHelpPopover helpText="Help copy." headerContent="Field" />)
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })
})

describe('createFieldHelp', () => {
  it('creates a More info popover with the given header and body', async () => {
    const user = userEvent.setup()
    render(createFieldHelp('Organization', 'Select the AAP organization.'))

    await user.click(screen.getByRole('button', { name: 'More info for Organization' }))
    expect(screen.getByText('Organization')).toBeInTheDocument()
    expect(screen.getByText('Select the AAP organization.')).toBeInTheDocument()
  })
})
