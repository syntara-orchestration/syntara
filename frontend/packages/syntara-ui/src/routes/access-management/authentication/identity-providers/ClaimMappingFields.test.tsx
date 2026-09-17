import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useForm, FormProvider } from 'react-hook-form'
import { describe, expect, it } from 'vitest'
import { axe } from 'vitest-axe'

import { UserClaimMappingFields } from './ClaimMappingFields'
import { identityProviderDefaults, type IdentityProviderFormData } from './identityProviderFormSchema'

function UserClaimWrapper({
  claimsSupported,
  claimAliases,
  isReadOnly,
}: {
  claimsSupported?: string[] | null
  claimAliases?: Record<string, string[]> | null
  isReadOnly?: boolean
}) {
  const methods = useForm<IdentityProviderFormData>({ defaultValues: identityProviderDefaults })
  return (
    <FormProvider {...methods}>
      <form>
        <UserClaimMappingFields
          control={methods.control}
          claimsSupported={claimsSupported}
          claimAliases={claimAliases}
          isReadOnly={isReadOnly}
        />
      </form>
    </FormProvider>
  )
}

describe('UserClaimMappingFields', () => {
  it('renders all user claim fields', () => {
    render(<UserClaimWrapper />)

    expect(screen.getByText('Subject claim')).toBeInTheDocument()
    expect(screen.getByText('Email claim')).toBeInTheDocument()
    expect(screen.getByText('Username claim')).toBeInTheDocument()
    expect(screen.getByText('First name claim')).toBeInTheDocument()
    expect(screen.getByText('Last name claim')).toBeInTheDocument()
  })

  it('renders text inputs with default values when no claimsSupported provided', () => {
    render(<UserClaimWrapper />)

    expect(screen.getByDisplayValue('sub')).toBeInTheDocument()
    expect(screen.getByDisplayValue('email')).toBeInTheDocument()
    expect(screen.getByDisplayValue('preferred_username')).toBeInTheDocument()
    expect(screen.getByDisplayValue('given_name')).toBeInTheDocument()
    expect(screen.getByDisplayValue('family_name')).toBeInTheDocument()
  })

  it('renders dropdowns when claimsSupported is provided', () => {
    const claimsSupported = ['sub', 'email', 'name', 'preferred_username']
    const claimAliases = {
      sub: ['sub'],
      email: ['email', 'mail'],
      username: ['preferred_username'],
      first_name: ['given_name', 'givenName'],
      last_name: ['family_name', 'familyName'],
    }

    render(<UserClaimWrapper claimsSupported={claimsSupported} claimAliases={claimAliases} />)

    // With typeahead Select, the selected value is displayed in a text input
    expect(screen.getByDisplayValue('sub')).toBeInTheDocument()
    expect(screen.getByDisplayValue('email')).toBeInTheDocument()
  })

  it('allows selecting a claim from the dropdown', async () => {
    const user = userEvent.setup()
    const claimsSupported = ['sub', 'email', 'mail', 'name', 'preferred_username']
    const claimAliases = { email: ['email', 'mail'] }

    render(<UserClaimWrapper claimsSupported={claimsSupported} claimAliases={claimAliases} />)

    // Click the email field's displayed value to open the dropdown
    const emailValue = screen.getByDisplayValue('email')
    await user.click(emailValue)

    // Select 'mail' from the dropdown
    const mailOption = await screen.findByRole('option', { name: 'mail' })
    await user.click(mailOption)

    // Verify the value changed
    expect(screen.getByDisplayValue('mail')).toBeInTheDocument()
  })

  it('switches to custom text input when Custom option is selected', async () => {
    const user = userEvent.setup()
    const claimsSupported = ['sub', 'email', 'name', 'preferred_username']

    render(<UserClaimWrapper claimsSupported={claimsSupported} />)

    // Open the Subject Claim dropdown via displayed value
    const subjectValue = screen.getByDisplayValue('sub')
    await user.click(subjectValue)

    // Select 'Custom...'
    const customOption = await screen.findByRole('option', { name: 'Custom...' })
    await user.click(customOption)

    // Should now show a text input — the component switches to TextInput mode
    // The field retains its current value ('sub') in the text input
    const textInput = screen.getByDisplayValue('sub')
    await user.clear(textInput)
    await user.type(textInput, 'my_custom_sub')

    expect(screen.getByDisplayValue('my_custom_sub')).toBeInTheDocument()
  })

  it('filters dropdown options when typing in typeahead', async () => {
    const user = userEvent.setup()
    const claimsSupported = ['sub', 'email', 'mail', 'name', 'preferred_username', 'upn']
    const claimAliases = { email: ['email', 'mail', 'upn'] }

    render(<UserClaimWrapper claimsSupported={claimsSupported} claimAliases={claimAliases} />)

    // Click the email displayed value to open dropdown, then type to filter
    const emailValue = screen.getByDisplayValue('email')
    await user.click(emailValue)
    await user.clear(emailValue)
    await user.type(emailValue, 'ma')

    // 'mail' should be visible, 'sub' should not
    expect(screen.getByRole('option', { name: 'mail' })).toBeInTheDocument()
    expect(screen.queryByRole('option', { name: 'sub' })).not.toBeInTheDocument()
  })

  it('renders read-only fields with disabled text inputs', () => {
    render(<UserClaimWrapper isReadOnly />)

    const inputs = screen.getAllByRole('textbox')
    for (const input of inputs) {
      expect(input).toBeDisabled()
    }
  })

  it('renders text inputs when claimsSupported is null', () => {
    render(<UserClaimWrapper claimsSupported={null} />)

    const inputs = screen.getAllByRole('textbox')
    // All five fields should render as plain text inputs
    expect(inputs.length).toBe(5)
    expect(screen.getByDisplayValue('sub')).toBeInTheDocument()
  })

  it('renders text inputs when claimsSupported is undefined', () => {
    render(<UserClaimWrapper claimsSupported={undefined} />)

    const inputs = screen.getAllByRole('textbox')
    expect(inputs.length).toBe(5)
  })

  it('shows "No claims match" message when filter matches nothing', async () => {
    const user = userEvent.setup()
    const claimsSupported = ['sub', 'email', 'name']

    render(<UserClaimWrapper claimsSupported={claimsSupported} />)

    const subjectValue = screen.getByDisplayValue('sub')
    await user.click(subjectValue)
    await user.clear(subjectValue)
    await user.type(subjectValue, 'zzzznonexistent')

    expect(screen.getByText(/No claims match/)).toBeInTheDocument()
    // The Custom... option should still be visible
    expect(screen.getByRole('option', { name: 'Custom...' })).toBeInTheDocument()
  })

  it('clears filter when a selection is made', async () => {
    const user = userEvent.setup()
    const claimsSupported = ['sub', 'email', 'name', 'preferred_username']

    render(<UserClaimWrapper claimsSupported={claimsSupported} />)

    // Open the dropdown and type a filter
    const subjectInput = screen.getByDisplayValue('sub')
    await user.click(subjectInput)
    await user.clear(subjectInput)
    await user.type(subjectInput, 'na')

    // Only 'name' should match the filter
    expect(screen.getByRole('option', { name: 'name' })).toBeInTheDocument()
    expect(screen.queryByRole('option', { name: 'sub' })).not.toBeInTheDocument()

    // Select 'name' to close and clear filter
    await user.click(screen.getByRole('option', { name: 'name' }))

    // Subject claim value should now be 'name'
    expect(screen.getByDisplayValue('name')).toBeInTheDocument()
  })

  it('renders read-only text inputs even when claimsSupported is provided', () => {
    const claimsSupported = ['sub', 'email', 'name', 'preferred_username']

    render(<UserClaimWrapper claimsSupported={claimsSupported} isReadOnly />)

    // Should render text inputs (not dropdowns) because isReadOnly overrides showDropdown
    const inputs = screen.getAllByRole('textbox')
    for (const input of inputs) {
      expect(input).toBeDisabled()
    }
  })

  it('displays read-only helper text when isReadOnly is true', () => {
    render(<UserClaimWrapper isReadOnly />)

    const helperTexts = screen.getAllByText('Pre-configured by provider template. Select Custom to modify.')
    expect(helperTexts.length).toBe(5)
  })

  it('orders matched aliases before other claims in dropdown', async () => {
    const user = userEvent.setup()
    const claimsSupported = ['alpha', 'beta', 'email', 'gamma', 'mail']
    const claimAliases = { email: ['email', 'mail'] }

    render(<UserClaimWrapper claimsSupported={claimsSupported} claimAliases={claimAliases} />)

    // Open the email dropdown
    const emailValue = screen.getByDisplayValue('email')
    await user.click(emailValue)

    const options = screen.getAllByRole('option')
    // The aliases (email, mail) should appear before other claims (alpha, beta, gamma)
    const optionTexts = options.map((opt) => opt.textContent)
    const emailIndex = optionTexts.indexOf('email')
    const mailIndex = optionTexts.indexOf('mail')
    const alphaIndex = optionTexts.indexOf('alpha')
    expect(emailIndex).toBeLessThan(alphaIndex)
    expect(mailIndex).toBeLessThan(alphaIndex)
  })

  it('handles claimAliases being null', () => {
    const claimsSupported = ['sub', 'email', 'name']

    render(<UserClaimWrapper claimsSupported={claimsSupported} claimAliases={null} />)

    // Should render dropdowns with all claims in original order
    expect(screen.getByDisplayValue('sub')).toBeInTheDocument()
  })

  it('handles claimAliases being undefined', () => {
    const claimsSupported = ['sub', 'email', 'name']

    render(<UserClaimWrapper claimsSupported={claimsSupported} claimAliases={undefined} />)

    expect(screen.getByDisplayValue('sub')).toBeInTheDocument()
  })

  it('handles claimAliases with no matching syntara field key', () => {
    const claimsSupported = ['sub', 'email', 'name']
    const claimAliases = { unrelated_field: ['something'] }

    render(<UserClaimWrapper claimsSupported={claimsSupported} claimAliases={claimAliases} />)

    // Should still render dropdowns with all claims
    expect(screen.getByDisplayValue('sub')).toBeInTheDocument()
  })

  it('opens dropdown when typing in the typeahead input while closed', async () => {
    const user = userEvent.setup()
    const claimsSupported = ['sub', 'email', 'name', 'preferred_username']

    render(<UserClaimWrapper claimsSupported={claimsSupported} />)

    // The input should show the current value
    const subjectInput = screen.getByDisplayValue('sub')

    // Type directly into the input without clicking first to open
    await user.clear(subjectInput)
    await user.type(subjectInput, 'na')

    // Dropdown should now be open with filtered options
    expect(screen.getByRole('option', { name: 'name' })).toBeInTheDocument()
  })

  it('shows all options when filter is empty', async () => {
    const user = userEvent.setup()
    const claimsSupported = ['sub', 'email', 'name']

    render(<UserClaimWrapper claimsSupported={claimsSupported} />)

    const subjectInput = screen.getByDisplayValue('sub')
    await user.click(subjectInput)

    // All options should be visible when no filter is applied
    expect(screen.getByRole('option', { name: 'sub' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'email' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'name' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'Custom...' })).toBeInTheDocument()
  })

  it('allows typing a custom value after switching to custom mode', async () => {
    const user = userEvent.setup()
    const claimsSupported = ['sub', 'email', 'name']

    render(<UserClaimWrapper claimsSupported={claimsSupported} />)

    // Open email dropdown and select Custom
    const emailValue = screen.getByDisplayValue('email')
    await user.click(emailValue)
    const customOption = await screen.findByRole('option', { name: 'Custom...' })
    await user.click(customOption)

    // Should now be a text input where we can type freely
    const textInput = screen.getByDisplayValue('email')
    await user.clear(textInput)
    await user.type(textInput, 'my_email_claim')

    expect(screen.getByDisplayValue('my_email_claim')).toBeInTheDocument()
  })

  it('renders helper hint text for each field when not read-only', () => {
    render(<UserClaimWrapper />)

    expect(screen.getByText(/IdP claim for the unique user identifier/)).toBeInTheDocument()
    expect(screen.getByText(/IdP claim for the user email/)).toBeInTheDocument()
    expect(screen.getByText(/IdP claim for the username/)).toBeInTheDocument()
    expect(screen.getByText(/IdP claim for the first name/)).toBeInTheDocument()
    expect(screen.getByText(/IdP claim for the last name/)).toBeInTheDocument()
  })

  it('handles empty claimsSupported array', async () => {
    const user = userEvent.setup()
    render(<UserClaimWrapper claimsSupported={[]} />)

    // Should render dropdowns (claimsSupported is truthy even if empty)
    const subjectInput = screen.getByDisplayValue('sub')
    await user.click(subjectInput)

    // Only Custom... option should be present since there are no claims
    const options = screen.getAllByRole('option')
    expect(options).toHaveLength(1)
    expect(screen.getByRole('option', { name: 'Custom...' })).toBeInTheDocument()
  })

  it('selects a claim and updates the displayed value', async () => {
    const user = userEvent.setup()
    const claimsSupported = ['sub', 'subject_id', 'user_id']
    const claimAliases = { sub: ['sub', 'subject_id'] }

    render(<UserClaimWrapper claimsSupported={claimsSupported} claimAliases={claimAliases} />)

    // Open subject dropdown
    const subjectInput = screen.getByDisplayValue('sub')
    await user.click(subjectInput)

    // Select a different claim
    const option = screen.getByRole('option', { name: 'subject_id' })
    await user.click(option)

    // Value should be updated
    expect(screen.getByDisplayValue('subject_id')).toBeInTheDocument()
  })

  it('closes dropdown and clears filter when pressing Escape', async () => {
    const user = userEvent.setup()
    const claimsSupported = ['sub', 'email', 'name', 'preferred_username']

    render(<UserClaimWrapper claimsSupported={claimsSupported} />)

    // Open the dropdown and type a filter
    const subjectInput = screen.getByDisplayValue('sub')
    await user.click(subjectInput)
    await user.clear(subjectInput)
    await user.type(subjectInput, 'em')

    // Only filtered options should be visible ('email' + 'Custom...')
    const filteredOptions = screen.getAllByRole('option')
    expect(filteredOptions.length).toBe(2)

    // Press Escape to close — this triggers onOpenChange(false) which clears filter
    await user.keyboard('{Escape}')

    // After closing with Escape, the input should show the original field value, not filter text
    // The onOpenChange(false) handler clears the filterValue
    expect(screen.getByDisplayValue('sub')).toBeInTheDocument()
  })

  it('toggles dropdown open and closed via the menu toggle button', async () => {
    const user = userEvent.setup()
    const claimsSupported = ['sub', 'email', 'name']

    render(<UserClaimWrapper claimsSupported={claimsSupported} />)

    // Find the first toggle button (Subject claim)
    const toggleButtons = screen.getAllByRole('button', { name: 'Menu toggle' })
    const subjectToggle = toggleButtons[0]

    // Click to open
    await user.click(subjectToggle)
    expect(screen.getByRole('option', { name: 'sub' })).toBeInTheDocument()

    // Click again to close
    await user.click(subjectToggle)
    await waitFor(() => {
      expect(screen.queryByRole('option', { name: 'sub' })).not.toBeInTheDocument()
    })
  })

  it('has no accessibility violations with dropdowns', async () => {
    const claimsSupported = ['sub', 'email', 'name', 'preferred_username']
    const { container } = render(<UserClaimWrapper claimsSupported={claimsSupported} />)
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('has no accessibility violations when read-only', async () => {
    const { container } = render(<UserClaimWrapper isReadOnly />)
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('has no accessibility violations', async () => {
    const { container } = render(<UserClaimWrapper />)
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })
})
