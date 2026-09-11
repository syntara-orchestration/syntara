import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { CredentialEmptyState } from './CredentialEmptyState'

describe('CredentialEmptyState', () => {
  it('renders empty state message', () => {
    render(<CredentialEmptyState onCreateCredential={vi.fn()} />)

    expect(screen.getByText('No credentials yet')).toBeInTheDocument()
  })

  it('renders description text', () => {
    render(<CredentialEmptyState onCreateCredential={vi.fn()} />)

    expect(screen.getByText(/Credentials provide secure authentication/i)).toBeInTheDocument()
  })

  it('renders create credential button', () => {
    render(<CredentialEmptyState onCreateCredential={vi.fn()} />)

    expect(screen.getByRole('button', { name: 'Create credential' })).toBeInTheDocument()
  })

  it('calls onCreateCredential when button is clicked', async () => {
    const user = userEvent.setup()
    const onCreateCredential = vi.fn()
    render(<CredentialEmptyState onCreateCredential={onCreateCredential} />)

    await user.click(screen.getByRole('button', { name: 'Create credential' }))

    expect(onCreateCredential).toHaveBeenCalledOnce()
  })

  it('does not render create button when onCreateCredential is omitted', () => {
    render(<CredentialEmptyState />)

    expect(screen.getByText('No credentials yet')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Create credential' })).not.toBeInTheDocument()
  })
})
