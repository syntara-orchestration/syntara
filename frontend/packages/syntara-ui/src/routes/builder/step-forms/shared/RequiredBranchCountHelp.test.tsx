import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { axe } from 'vitest-axe'

import { RequiredBranchCountHelp } from './RequiredBranchCountHelp'

describe('RequiredBranchCountHelp', () => {
  it('renders help icon button', () => {
    render(<RequiredBranchCountHelp />)
    expect(screen.getByRole('button', { name: /more info/i })).toBeInTheDocument()
  })

  it('shows popover content when clicked', async () => {
    const user = userEvent.setup()
    render(<RequiredBranchCountHelp />)

    await user.click(screen.getByRole('button', { name: /more info/i }))

    expect(screen.getByText(/minimum number of incoming branches/i)).toBeInTheDocument()
    expect(screen.getByText(/any two of the three branches finish/i)).toBeInTheDocument()
  })

  it('has no accessibility violations', async () => {
    const { container } = render(<RequiredBranchCountHelp />)
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })
})
