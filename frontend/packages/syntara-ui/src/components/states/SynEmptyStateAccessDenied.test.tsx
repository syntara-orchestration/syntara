import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { axe } from 'vitest-axe'

import { SynEmptyStateAccessDenied } from './SynEmptyStateAccessDenied'

describe('SynEmptyStateAccessDenied', () => {
  it('has no accessibility violations', async () => {
    const { container } = render(
      <SynEmptyStateAccessDenied description="You don't have permission to view settings." />
    )

    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('renders the access denied title', () => {
    render(<SynEmptyStateAccessDenied description="Contact your administrator." />)

    expect(screen.getByRole('heading', { name: 'Access denied', level: 2 })).toBeInTheDocument()
  })

  it('renders the provided description', () => {
    render(<SynEmptyStateAccessDenied description="You don't have permission to view this resource." />)

    expect(screen.getByText("You don't have permission to view this resource.")).toBeInTheDocument()
  })

  it('renders when description is empty', () => {
    render(<SynEmptyStateAccessDenied description="" />)

    expect(screen.getByRole('heading', { name: 'Access denied', level: 2 })).toBeInTheDocument()
  })
})
