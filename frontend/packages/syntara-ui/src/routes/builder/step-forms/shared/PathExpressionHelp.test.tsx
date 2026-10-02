import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import { PathExpressionHelp } from './PathExpressionHelp'

describe('PathExpressionHelp', () => {
  it('renders help icon button', () => {
    render(<PathExpressionHelp />)
    expect(screen.getByRole('button', { name: /more info/i })).toBeInTheDocument()
  })

  it('shows popover content when clicked', async () => {
    const user = userEvent.setup()
    render(<PathExpressionHelp />)

    await user.click(screen.getByRole('button', { name: /more info/i }))

    expect(screen.getByText(/Visual expression builder/i)).toBeInTheDocument()
    expect(screen.getByText(/Custom expression/i)).toBeInTheDocument()
  })

  it('displays path-specific description in popover', async () => {
    const user = userEvent.setup()
    render(<PathExpressionHelp />)

    await user.click(screen.getByRole('button', { name: /more info/i }))

    expect(screen.getByText(/first path whose condition evaluates to true/i)).toBeInTheDocument()
  })
})
