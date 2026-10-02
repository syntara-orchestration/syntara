import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { axe } from 'vitest-axe'

import { ExpressionHelpPopover } from './ExpressionHelpPopover'

describe('ExpressionHelpPopover', () => {
  it('renders More info button with header', () => {
    render(<ExpressionHelpPopover headerContent="Condition" description="When to take this path." />)
    expect(screen.getByRole('button', { name: 'More info for Condition' })).toBeInTheDocument()
  })

  it('shows description and builder guidance when clicked', async () => {
    const user = userEvent.setup()
    render(<ExpressionHelpPopover headerContent="Condition" description="When to take this path." />)

    await user.click(screen.getByRole('button', { name: 'More info for Condition' }))

    expect(screen.getByText('When to take this path.')).toBeInTheDocument()
    expect(screen.getByText(/Visual expression builder/i)).toBeInTheDocument()
    expect(screen.getByText(/Custom expression/i)).toBeInTheDocument()
  })

  it('has no accessibility violations', async () => {
    const { container } = render(
      <ExpressionHelpPopover headerContent="Condition" description="When to take this path." />
    )
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })
})
