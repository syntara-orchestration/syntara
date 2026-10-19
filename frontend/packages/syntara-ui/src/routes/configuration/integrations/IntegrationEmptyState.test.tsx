import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { IntegrationEmptyState } from './IntegrationEmptyState'

describe('IntegrationEmptyState', () => {
  it('renders empty state message', () => {
    render(<IntegrationEmptyState />)

    expect(screen.getByText('No integrations yet')).toBeInTheDocument()
  })

  it('renders description text', () => {
    render(<IntegrationEmptyState />)

    expect(screen.getByText(/Configure integrations to connect external tools and services/i)).toBeInTheDocument()
  })

  it('renders a configure integration link', () => {
    render(<IntegrationEmptyState />)

    expect(screen.getByRole('link', { name: 'Configure integration' })).toHaveAttribute(
      'href',
      '/configuration/integrations/configure'
    )
  })

  it('omits the configure link when the user cannot create integrations', () => {
    render(<IntegrationEmptyState canCreate={false} />)

    expect(screen.queryByRole('link', { name: 'Configure integration' })).not.toBeInTheDocument()
  })
})
