import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it } from 'vitest'

import { routerTestState } from '../../../test/setup'

import { IntegrationEmptyState } from './IntegrationEmptyState'

describe('IntegrationEmptyState', () => {
  beforeEach(() => {
    routerTestState.navigate.mockClear()
  })

  it('renders empty state message', () => {
    render(<IntegrationEmptyState />)

    expect(screen.getByText('No integrations yet')).toBeInTheDocument()
  })

  it('renders description text', () => {
    render(<IntegrationEmptyState />)

    expect(screen.getByText(/Configure integrations to connect external tools and services/i)).toBeInTheDocument()
  })

  it('renders configure integration button', () => {
    render(<IntegrationEmptyState />)

    expect(screen.getByRole('button', { name: 'Configure integration' })).toBeInTheDocument()
  })

  it('navigates to configure page when button is clicked', async () => {
    const user = userEvent.setup()
    render(<IntegrationEmptyState />)

    const addButton = screen.getByRole('button', { name: 'Configure integration' })
    await user.click(addButton)

    expect(routerTestState.navigate).toHaveBeenCalledWith(
      expect.objectContaining({ to: '/configuration/integrations/configure' })
    )
  })
})
