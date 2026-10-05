import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useForm } from 'react-hook-form'
import { describe, expect, it } from 'vitest'
import { axe } from 'vitest-axe'

import { IdentityProviderFormFields } from './IdentityProviderFormFields'
import { identityProviderDefaults, type IdentityProviderFormData } from './identityProviderFormSchema'
import { IdpTypeKey } from './idpTypePresets'

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false } },
})

const completedDefaults = {
  ...identityProviderDefaults,
  idpType: IdpTypeKey.CUSTOM,
  issuerUrl: 'https://example.com',
  clientId: 'test-client',
}

const aapDefaults = {
  ...identityProviderDefaults,
  idpType: IdpTypeKey.AAP,
  issuerUrl: 'https://aap.example.com',
  clientId: 'aap-client',
  aapRoleMappingEnabled: true,
}

function TestWrapper({ isEdit = false, defaults }: { isEdit?: boolean; defaults?: IdentityProviderFormData }) {
  const methods = useForm<IdentityProviderFormData>({
    defaultValues: defaults ?? completedDefaults,
  })

  return (
    <QueryClientProvider client={queryClient}>
      <form>
        <IdentityProviderFormFields form={methods} isEdit={isEdit} testResult={null} />
      </form>
    </QueryClientProvider>
  )
}

describe('IdentityProviderFormFields', () => {
  it('renders provider name field', () => {
    render(<TestWrapper />)

    expect(screen.getByLabelText(/Provider name/)).toBeInTheDocument()
  })

  it('renders enable provider switch', () => {
    render(<TestWrapper />)

    expect(screen.getByLabelText(/Enabled/)).toBeInTheDocument()
  })

  it('renders auto-discovery switch', () => {
    render(<TestWrapper />)

    expect(screen.getByLabelText(/Use OIDC Discovery/)).toBeInTheDocument()
  })

  it('renders issuer URL field', () => {
    render(<TestWrapper />)

    expect(screen.getByLabelText(/Issuer URL/)).toBeInTheDocument()
  })

  it('renders client ID field', () => {
    render(<TestWrapper />)

    expect(screen.getByLabelText(/Client ID/)).toBeInTheDocument()
  })

  it('renders client secret field as required in add mode', () => {
    render(<TestWrapper />)

    expect(screen.getByLabelText(/Client secret/)).toBeInTheDocument()
  })

  it('renders redirect URI as read-only clipboard copy', () => {
    render(<TestWrapper />)

    expect(screen.getByText(/Redirect URI/)).toBeInTheDocument()
    expect(screen.getByDisplayValue(/\/api\/v1\/auth\/oidc\/callback/)).toBeInTheDocument()
  })

  it('renders scopes field with default value', () => {
    render(<TestWrapper />)

    expect(screen.getByText('openid')).toBeInTheDocument()
    expect(screen.getByText('profile')).toBeInTheDocument()
    expect(screen.getByText('email')).toBeInTheDocument()
  })

  it('hides manual endpoint fields when auto-discovery is enabled', () => {
    render(<TestWrapper />)

    expect(screen.queryByLabelText(/Authorization endpoint/)).not.toBeInTheDocument()
    expect(screen.queryByLabelText(/Token endpoint/)).not.toBeInTheDocument()
    expect(screen.queryByLabelText(/JWKS URI/)).not.toBeInTheDocument()
  })

  it('shows manual endpoint fields when auto-discovery is toggled off', async () => {
    const user = userEvent.setup()
    render(<TestWrapper />)

    await user.click(screen.getByLabelText(/Use OIDC Discovery/))

    expect(screen.getByLabelText(/Authorization endpoint/)).toBeInTheDocument()
    expect(screen.getByLabelText(/Token endpoint/)).toBeInTheDocument()
    expect(screen.getByLabelText(/JWKS URI/)).toBeInTheDocument()
    expect(screen.getByLabelText(/Userinfo endpoint/)).toBeInTheDocument()
  })

  it('shows hint text for client secret in edit mode', () => {
    render(<TestWrapper isEdit />)

    expect(screen.getByText(/Leave empty to keep the existing secret/)).toBeInTheDocument()
  })

  it('renders wizard with two steps', () => {
    render(<TestWrapper />)

    expect(screen.getByRole('button', { name: /Provider configuration/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Claim mapping/ })).toBeInTheDocument()
  })

  it('shows claim mapping fields including groups on second step', async () => {
    const user = userEvent.setup()
    render(<TestWrapper />)

    await user.click(screen.getByRole('button', { name: /Claim mapping/ }))

    expect(screen.getByText('Subject claim')).toBeInTheDocument()
    expect(screen.getByText('Email claim')).toBeInTheDocument()
    expect(screen.getByText('Username claim')).toBeInTheDocument()
    expect(screen.getByText('First name claim')).toBeInTheDocument()
    expect(screen.getByText('Last name claim')).toBeInTheDocument()
  })

  it('shows Next button on first step', () => {
    render(<TestWrapper />)

    expect(screen.getByRole('button', { name: 'Next' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Back' })).not.toBeInTheDocument()
  })

  it('shows Back button and no Next on last step', async () => {
    const user = userEvent.setup()
    render(<TestWrapper />)

    await user.click(screen.getByRole('button', { name: /Claim mapping/ }))

    expect(screen.getByRole('button', { name: 'Back' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Next' })).not.toBeInTheDocument()
  })

  it('renders single logout switch with accessible label', () => {
    render(<TestWrapper />)

    expect(screen.getByLabelText(/Single logout/)).toBeInTheDocument()
  })

  it('renders allow all authenticated switch', () => {
    render(<TestWrapper />)

    expect(screen.getByLabelText(/Allow all authenticated/)).toBeInTheDocument()
  })

  it('shows warning when allow all authenticated is enabled', async () => {
    const user = userEvent.setup()
    render(<TestWrapper />)

    const toggle = screen.getByLabelText(/Allow all authenticated/)
    await user.click(toggle)

    expect(screen.getByText(/any user who authenticates via this provider will be granted access/i)).toBeInTheDocument()
  })

  it('has no accessibility violations', async () => {
    const { container } = render(<TestWrapper />)

    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('shows AAP role mapping toggle when AAP template is selected', () => {
    render(<TestWrapper defaults={aapDefaults} />)

    expect(screen.getByLabelText(/Map AAP system roles to groups/)).toBeInTheDocument()
  })

  it('hides AAP role mapping toggle for custom template', () => {
    render(<TestWrapper />)

    expect(screen.queryByLabelText(/Map AAP system roles to groups/)).not.toBeInTheDocument()
  })

  it('has no accessibility violations with AAP template', async () => {
    const { container } = render(<TestWrapper defaults={aapDefaults} />)

    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('toggles AAP role mapping switch off and on', async () => {
    const user = userEvent.setup()
    render(<TestWrapper defaults={aapDefaults} />)

    const toggle = screen.getByLabelText(/Map AAP system roles to groups/)
    expect(toggle).toBeChecked()

    await user.click(toggle)
    expect(toggle).not.toBeChecked()

    await user.click(toggle)
    expect(toggle).toBeChecked()
  })

  it('prefills AAP role mapping and single logout when AAP template is selected', async () => {
    const user = userEvent.setup()
    render(<TestWrapper />)

    const templateButton = screen.getByRole('button', { name: /Custom/ })
    await user.click(templateButton)
    await user.click(screen.getByRole('option', { name: /Ansible Automation Platform/ }))

    expect(screen.getByLabelText(/Map AAP system roles to groups/)).toBeChecked()
    expect(screen.getByLabelText(/Single logout/)).toBeChecked()
  })
})
