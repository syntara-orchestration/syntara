import type { IdentityProvidersAPI } from '@syntara/contracts'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { DisableIdentityProviderDialog } from './DisableIdentityProviderDialog'

type IdentityProvider = IdentityProvidersAPI.components['schemas']['IdentityProviderRead']

const mockProvider = {
  id: 'idp-1',
  name: 'Okta SSO',
  enabled: true,
  configuration: {
    issuer_url: 'https://example.okta.com',
    client_id: 'client-123',
  },
} as IdentityProvider

describe('DisableIdentityProviderDialog', () => {
  it('returns null when provider is null', () => {
    render(<DisableIdentityProviderDialog provider={null} onConfirm={vi.fn()} onClose={vi.fn()} />)
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('renders dialog with provider name', () => {
    render(<DisableIdentityProviderDialog provider={mockProvider} onConfirm={vi.fn()} onClose={vi.fn()} />)

    expect(screen.getByText('Disable identity provider?')).toBeInTheDocument()
    expect(screen.getByText('Okta SSO')).toBeInTheDocument()
  })

  it('shows re-enable message', () => {
    render(<DisableIdentityProviderDialog provider={mockProvider} onConfirm={vi.fn()} onClose={vi.fn()} />)

    expect(screen.getByText(/You can re-enable the identity provider at any time/)).toBeInTheDocument()
  })

  it('shows consequence text about sign-in', () => {
    render(<DisableIdentityProviderDialog provider={mockProvider} onConfirm={vi.fn()} onClose={vi.fn()} />)

    expect(screen.getByText(/Users will no longer be able to sign in/)).toBeInTheDocument()
  })

  it('has confirm button with primary variant (not danger)', () => {
    render(<DisableIdentityProviderDialog provider={mockProvider} onConfirm={vi.fn()} onClose={vi.fn()} />)

    const disableButton = screen.getByRole('button', { name: 'Disable' })
    expect(disableButton).toBeEnabled()
    expect(disableButton.classList.contains('pf-m-danger')).toBe(false)
  })

  it('does not show a warning icon or acknowledgement checkbox', () => {
    render(<DisableIdentityProviderDialog provider={mockProvider} onConfirm={vi.fn()} onClose={vi.fn()} />)

    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument()
  })

  it('calls onConfirm when Disable button clicked', async () => {
    const user = userEvent.setup()
    const mockOnConfirm = vi.fn()

    render(<DisableIdentityProviderDialog provider={mockProvider} onConfirm={mockOnConfirm} onClose={vi.fn()} />)

    await user.click(screen.getByRole('button', { name: 'Disable' }))
    expect(mockOnConfirm).toHaveBeenCalledTimes(1)
  })

  it('calls onClose when Cancel button clicked', async () => {
    const user = userEvent.setup()
    const mockOnClose = vi.fn()

    render(<DisableIdentityProviderDialog provider={mockProvider} onConfirm={vi.fn()} onClose={mockOnClose} />)

    await user.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(mockOnClose).toHaveBeenCalledTimes(1)
  })

  it('disables buttons while isLoading is true', () => {
    render(
      <DisableIdentityProviderDialog provider={mockProvider} isLoading={true} onConfirm={vi.fn()} onClose={vi.fn()} />
    )

    expect(screen.getByRole('button', { name: /Disable/ })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeDisabled()
  })

  it('enables buttons when isLoading is false', () => {
    render(
      <DisableIdentityProviderDialog provider={mockProvider} isLoading={false} onConfirm={vi.fn()} onClose={vi.fn()} />
    )

    expect(screen.getByRole('button', { name: 'Disable' })).toBeEnabled()
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeEnabled()
  })

  it('has no accessibility violations', async () => {
    const { container } = render(
      <DisableIdentityProviderDialog provider={mockProvider} onConfirm={vi.fn()} onClose={vi.fn()} />
    )

    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })
})
