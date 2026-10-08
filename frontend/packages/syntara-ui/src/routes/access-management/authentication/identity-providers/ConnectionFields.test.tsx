import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useForm, FormProvider } from 'react-hook-form'
import { describe, expect, it } from 'vitest'
import { axe } from 'vitest-axe'

import { ConnectionFields } from './ConnectionFields'
import { type IdentityProviderFormData, identityProviderDefaults } from './identityProviderFormSchema'

function Wrapper({
  autoDiscovery = true,
  isEdit = false,
  disableTlsVerify = false,
}: {
  autoDiscovery?: boolean
  isEdit?: boolean
  disableTlsVerify?: boolean
}) {
  const methods = useForm<IdentityProviderFormData>({
    defaultValues: { ...identityProviderDefaults, autoDiscovery, disableTlsVerify },
  })
  return (
    <FormProvider {...methods}>
      <ConnectionFields autoDiscovery={autoDiscovery} isEdit={isEdit} />
    </FormProvider>
  )
}

describe('ConnectionFields', () => {
  it('renders issuer URL, client ID, and client secret fields', () => {
    render(<Wrapper />)

    expect(screen.getByLabelText(/Issuer URL/)).toBeInTheDocument()
    expect(screen.getByLabelText(/Client ID/)).toBeInTheDocument()
    expect(screen.getByLabelText(/Client secret/)).toBeInTheDocument()
  })

  it('renders the auto-discovery switch and toggles it', async () => {
    const user = userEvent.setup()
    render(<Wrapper />)

    const toggle = screen.getByRole('switch', { name: /Use OIDC Discovery/ })
    expect(toggle).toBeInTheDocument()

    await user.click(toggle)
    expect(toggle).not.toBeChecked()
  })

  it('does not render manual endpoint fields when auto-discovery is on', () => {
    render(<Wrapper autoDiscovery />)

    expect(screen.queryByLabelText(/Authorization endpoint/)).not.toBeInTheDocument()
  })

  it('renders manual endpoint fields when auto-discovery is off', () => {
    render(<Wrapper autoDiscovery={false} />)

    expect(screen.getByLabelText(/Authorization endpoint/)).toBeInTheDocument()
    expect(screen.getByLabelText(/Token endpoint/)).toBeInTheDocument()
    expect(screen.getByLabelText(/JWKS URI/)).toBeInTheDocument()
  })

  it('shows edit hint for client secret in edit mode', () => {
    render(<Wrapper isEdit />)

    expect(screen.getByText(/Leave empty to keep the existing secret/)).toBeInTheDocument()
  })

  it('does not show edit hint for client secret in create mode', () => {
    render(<Wrapper isEdit={false} />)

    expect(screen.queryByText(/Leave empty to keep the existing secret/)).not.toBeInTheDocument()
  })

  it('renders help icons for connection fields', async () => {
    const user = userEvent.setup()
    render(<Wrapper />)

    const helpButtons = screen.getAllByRole('button', { name: 'More info' })
    expect(helpButtons.length).toBeGreaterThanOrEqual(3)

    await user.click(helpButtons[0])
    expect(screen.getByText(/OpenID Connect provider/)).toBeInTheDocument()
  })

  it('renders the disable TLS verification switch', () => {
    render(<Wrapper />)

    expect(screen.getByLabelText(/Disable TLS certificate verification/)).toBeInTheDocument()
  })

  it('toggles the disable TLS verification switch', async () => {
    const user = userEvent.setup()
    render(<Wrapper />)

    const toggle = screen.getByLabelText(/Disable TLS certificate verification/)
    expect(toggle).not.toBeChecked()

    await user.click(toggle)
    expect(toggle).toBeChecked()
  })

  it('unchecks the disable TLS verification switch when initially enabled', async () => {
    const user = userEvent.setup()
    render(<Wrapper disableTlsVerify />)

    const toggle = screen.getByLabelText(/Disable TLS certificate verification/)
    expect(toggle).toBeChecked()

    await user.click(toggle)
    expect(toggle).not.toBeChecked()
  })

  it('shows warning text for disable TLS verification', () => {
    render(<Wrapper />)

    expect(screen.getByText(/TLS certificate errors are ignored/)).toBeInTheDocument()
  })

  it('has no accessibility violations with auto-discovery on', async () => {
    const { container } = render(<Wrapper autoDiscovery />)
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('has no accessibility violations with auto-discovery off', async () => {
    const { container } = render(<Wrapper autoDiscovery={false} />)
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })
})
