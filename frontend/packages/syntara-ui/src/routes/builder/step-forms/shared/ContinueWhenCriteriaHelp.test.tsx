import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { axe } from 'vitest-axe'

import { ContinueWhenCriteriaHelp } from './ContinueWhenCriteriaHelp'

describe('ContinueWhenCriteriaHelp', () => {
  it('renders help icon button', () => {
    render(<ContinueWhenCriteriaHelp />)
    expect(screen.getByRole('button', { name: /more info/i })).toBeInTheDocument()
  })

  it('shows popover content when clicked', async () => {
    const user = userEvent.setup()
    render(<ContinueWhenCriteriaHelp />)

    await user.click(screen.getByRole('button', { name: /more info/i }))

    expect(screen.getByText(/All branches reach this step/i)).toBeInTheDocument()
    expect(screen.getByText(/Any branches reach this step/i)).toBeInTheDocument()
  })

  it('has no accessibility violations', async () => {
    const { container } = render(<ContinueWhenCriteriaHelp />)
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })
})
