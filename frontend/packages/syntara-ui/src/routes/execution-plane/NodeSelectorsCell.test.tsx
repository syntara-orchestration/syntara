import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { axe } from 'vitest-axe'

import { NodeSelectorsCell } from './NodeSelectorsCell'

describe('NodeSelectorsCell', () => {
  it('renders an em dash when there are no selectors', () => {
    render(<NodeSelectorsCell selectors={[]} />)
    expect(screen.getByText('—')).toBeInTheDocument()
  })

  it('renders selector chips', () => {
    render(<NodeSelectorsCell selectors={['workload=automation', 'region=us-west']} />)
    expect(screen.getByText('workload=automation')).toBeInTheDocument()
    expect(screen.getByText('region=us-west')).toBeInTheDocument()
  })

  it('has no accessibility violations', async () => {
    const { container } = render(<NodeSelectorsCell selectors={['env=prod']} />)
    expect(await axe(container)).toHaveNoViolations()
  })
})
