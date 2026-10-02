import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { axe } from 'vitest-axe'

import { WhileConditionHelp } from './WhileConditionHelp'

describe('WhileConditionHelp', () => {
  it('renders More info button', () => {
    render(<WhileConditionHelp />)
    expect(screen.getByRole('button', { name: /more info/i })).toBeInTheDocument()
  })

  it('shows while-loop help body when clicked', async () => {
    const user = userEvent.setup()
    render(<WhileConditionHelp />)

    await user.click(screen.getByRole('button', { name: /more info/i }))

    expect(screen.getByText(/loop body always runs at least once/i)).toBeInTheDocument()
    expect(screen.getAllByText(/Visual expression builder/i).length).toBeGreaterThanOrEqual(1)
  })

  it('has no accessibility violations', async () => {
    const { container } = render(<WhileConditionHelp />)
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })
})
