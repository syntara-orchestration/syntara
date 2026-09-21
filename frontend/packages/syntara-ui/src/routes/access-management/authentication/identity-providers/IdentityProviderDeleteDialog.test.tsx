import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { IdentityProviderDeleteDialog } from './IdentityProviderDeleteDialog'

describe('IdentityProviderDeleteDialog', () => {
  it('has no accessibility violations when open', async () => {
    const { baseElement } = render(
      <IdentityProviderDeleteDialog isOpen providerName="Azure AD" onClose={vi.fn()} onConfirm={vi.fn()} />
    )

    expect(await axe(baseElement)).toHaveNoViolations()
  })

  it('renders provider name and consequence list', () => {
    render(<IdentityProviderDeleteDialog isOpen providerName="Okta" onClose={vi.fn()} onConfirm={vi.fn()} />)

    expect(screen.getByText('Delete identity provider?')).toBeInTheDocument()
    expect(screen.getByText('Okta')).toBeInTheDocument()
    expect(screen.getByText(/will be deleted. This cannot be undone/)).toBeInTheDocument()
    expect(screen.getByText(/Remove all user identities linked to this provider/)).toBeInTheDocument()
  })

  it('keeps Delete disabled until acknowledgement is checked, then calls onConfirm', async () => {
    const user = userEvent.setup()
    const onConfirm = vi.fn()
    const onClose = vi.fn()

    render(<IdentityProviderDeleteDialog isOpen providerName="Okta" onClose={onClose} onConfirm={onConfirm} />)

    const dialog = screen.getByRole('dialog')
    const deleteButton = within(dialog).getByRole('button', { name: 'Delete identity provider' })

    expect(deleteButton).toBeDisabled()

    await user.click(
      within(dialog).getByRole('checkbox', {
        name: /I understand this identity provider and its linked identities will be permanently deleted/i,
      })
    )

    expect(deleteButton).toBeEnabled()
    await user.click(deleteButton)

    expect(onConfirm).toHaveBeenCalledTimes(1)
    expect(onClose).not.toHaveBeenCalled()
  })
})
