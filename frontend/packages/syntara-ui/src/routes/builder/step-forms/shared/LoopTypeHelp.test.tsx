import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { axe } from 'vitest-axe'

import { LoopTypeHelp } from './LoopTypeHelp'

describe('LoopTypeHelp', () => {
  it('renders More info button', () => {
    render(<LoopTypeHelp />)
    expect(screen.getByRole('button', { name: 'More info for Type' })).toBeInTheDocument()
  })

  it('shows for-each and while guidance when clicked', async () => {
    const user = userEvent.setup()
    render(<LoopTypeHelp />)

    await user.click(screen.getByRole('button', { name: 'More info for Type' }))

    expect(screen.getByText(/Best for processing lists/i)).toBeInTheDocument()
    expect(screen.getByText(/Best for repetitive checks/i)).toBeInTheDocument()
    expect(screen.getByText(/Static vs. dynamic/i)).toBeInTheDocument()
  })

  it('has no accessibility violations', async () => {
    const { container } = render(<LoopTypeHelp />)
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })
})
