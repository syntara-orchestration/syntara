import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { axe } from 'vitest-axe'

import { MaxIterationsHelp } from './MaxIterationsHelp'

describe('MaxIterationsHelp', () => {
  it('renders More info button', () => {
    render(<MaxIterationsHelp />)
    expect(screen.getByRole('button', { name: 'More info for Max iterations' })).toBeInTheDocument()
  })

  it('shows max iterations help body when clicked', async () => {
    const user = userEvent.setup()
    render(<MaxIterationsHelp />)

    await user.click(screen.getByRole('button', { name: 'More info for Max iterations' }))

    expect(screen.getByText(/maximum number of times/i)).toBeInTheDocument()
  })

  it('has no accessibility violations', async () => {
    const { container } = render(<MaxIterationsHelp />)
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })
})
