import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { axe } from 'vitest-axe'

import { SynLoadingState } from './SynLoadingState'

describe('SynLoadingState', () => {
  it('has no accessibility violations', async () => {
    const { container } = render(<SynLoadingState />)

    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('renders without crashing', () => {
    render(<SynLoadingState />)
    expect(screen.getByTestId('loading-state')).toBeInTheDocument()
  })

  it('displays a spinner with correct aria-label', () => {
    render(<SynLoadingState />)
    expect(screen.getByRole('progressbar', { name: 'Loading' })).toBeInTheDocument()
  })

  it('renders with centered layout', () => {
    render(<SynLoadingState />)
    const container = screen.getByTestId('loading-state')
    expect(container).toHaveClass('pf-v6-l-flex')
  })
})
