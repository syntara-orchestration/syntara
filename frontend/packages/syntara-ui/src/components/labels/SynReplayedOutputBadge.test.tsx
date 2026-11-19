import { render, screen } from '@testing-library/react'
import { axe } from 'vitest-axe'

import { SynReplayedOutputBadge } from './SynReplayedOutputBadge'

describe('SynReplayedOutputBadge', () => {
  it('states that the step reused output, so the meaning is not carried by colour alone', () => {
    render(<SynReplayedOutputBadge />)

    expect(screen.getByText('Reused output')).toBeInTheDocument()
  })

  it('has no accessibility violations', async () => {
    const { container } = render(<SynReplayedOutputBadge />)
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })
})
