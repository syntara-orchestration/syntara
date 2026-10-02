import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { axe } from 'vitest-axe'

import { ConditionalExpressionHelp } from './ConditionalExpressionHelp'

describe('ConditionalExpressionHelp', () => {
  it('renders help icon button', () => {
    render(<ConditionalExpressionHelp />)
    expect(screen.getByRole('button', { name: /more info/i })).toBeInTheDocument()
  })

  it('shows popover content when clicked', async () => {
    const user = userEvent.setup()
    render(<ConditionalExpressionHelp />)

    await user.click(screen.getByRole('button', { name: /more info/i }))

    expect(screen.getByText(/Visual expression builder/i)).toBeInTheDocument()
    expect(screen.getByText(/Custom expression/i)).toBeInTheDocument()
  })

  it('displays format hint in popover', async () => {
    const user = userEvent.setup()
    render(<ConditionalExpressionHelp />)

    await user.click(screen.getByRole('button', { name: /more info/i }))

    expect(screen.getByText(/\$\{variable operator value\}/)).toBeInTheDocument()
  })

  it('has no accessibility violations', async () => {
    const { container } = render(<ConditionalExpressionHelp />)
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })
})
