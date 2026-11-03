import { render, screen } from '@testing-library/react'
import { useForm, FormProvider } from 'react-hook-form'
import { describe, expect, it } from 'vitest'
import { axe } from 'vitest-axe'

import { type IdentityProviderFormData } from './identityProviderFormSchema'
import { ManualEndpointFields } from './ManualEndpointFields'

function Wrapper() {
  const methods = useForm<IdentityProviderFormData>({
    defaultValues: {
      authorizationEndpoint: '',
      tokenEndpoint: '',
      jwksUri: '',
      userinfoEndpoint: '',
      endSessionEndpoint: '',
    },
  })
  return (
    <FormProvider {...methods}>
      <ManualEndpointFields />
    </FormProvider>
  )
}

describe('ManualEndpointFields', () => {
  it('renders all endpoint fields', () => {
    render(<Wrapper />)

    expect(screen.getByLabelText(/authorization endpoint/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/token endpoint/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/jwks uri/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/userinfo endpoint/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/end session endpoint/i)).toBeInTheDocument()
  })

  it('has no accessibility violations', async () => {
    const { container } = render(<Wrapper />)
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })
})
