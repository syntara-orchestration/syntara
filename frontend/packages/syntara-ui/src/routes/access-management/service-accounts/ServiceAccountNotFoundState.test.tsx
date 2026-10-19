import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { ServiceAccountNotFoundState } from './ServiceAccountNotFoundState'

describe('ServiceAccountNotFoundState', () => {
  it('renders not-found heading and description', () => {
    render(<ServiceAccountNotFoundState backTo="/service-accounts" onRetry={vi.fn()} />)

    expect(screen.getByRole('heading', { name: 'Service account not found' })).toBeInTheDocument()
    expect(screen.getByText(/does not exist or may have been deleted/)).toBeInTheDocument()
  })

  it('renders a back link to service accounts', () => {
    render(<ServiceAccountNotFoundState backTo="/service-accounts" onRetry={vi.fn()} />)

    expect(screen.getByRole('link', { name: /back to service accounts/i })).toHaveAttribute('href', '/service-accounts')
  })

  it('calls onRetry when retry button is clicked', async () => {
    const onRetry = vi.fn()
    const user = userEvent.setup()
    render(<ServiceAccountNotFoundState backTo="/service-accounts" onRetry={onRetry} />)

    await user.click(screen.getByRole('button', { name: /retry/i }))
    expect(onRetry).toHaveBeenCalledOnce()
  })

  it('has no accessibility violations', async () => {
    const { container } = render(<ServiceAccountNotFoundState backTo="/service-accounts" onRetry={vi.fn()} />)

    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })
})
