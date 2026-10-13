import { render, screen } from '@testing-library/react'
import { axe } from 'vitest-axe'

import { ReplayedOutputBadge } from './ReplayedOutputBadge'

describe('ReplayedOutputBadge', () => {
  it('states that the step reused output, so the meaning is not carried by colour alone', () => {
    render(<ReplayedOutputBadge />)

    expect(screen.getByText('Reused output')).toBeInTheDocument()
  })

  it('has no accessibility violations', async () => {
    const { container } = render(<ReplayedOutputBadge />)
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })
})