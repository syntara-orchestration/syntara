import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { axe } from 'vitest-axe'

import { RoutingLabelsCell } from './RoutingLabelsCell'

describe('RoutingLabelsCell', () => {
  it('renders an em dash when there are no labels', () => {
    render(<RoutingLabelsCell labels={{}} />)
    expect(screen.getByText('—')).toBeInTheDocument()
  })

  it('renders key=value chips', () => {
    render(<RoutingLabelsCell labels={{ region: 'us-west', env: 'prod' }} />)
    expect(screen.getByText('region=us-west')).toBeInTheDocument()
    expect(screen.getByText('env=prod')).toBeInTheDocument()
  })

  it('has no accessibility violations', async () => {
    const { container } = render(<RoutingLabelsCell labels={{ env: 'prod' }} />)
    expect(await axe(container)).toHaveNoViolations()
  })
})
