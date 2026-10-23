import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { axe } from 'vitest-axe'

import { CREDENTIAL_TYPE_HELP } from './CredentialTypeHelp'

describe('CredentialTypeHelp', () => {
  it('describes Kafka as the SASL login for validation and listener runtime', () => {
    render(CREDENTIAL_TYPE_HELP)

    expect(
      screen.getByText(/SASL username and password for connector validation and listener runtime/)
    ).toBeInTheDocument()
  })

  it('has no accessibility violations', async () => {
    const { container } = render(CREDENTIAL_TYPE_HELP)

    expect(await axe(container)).toHaveNoViolations()
  })
})
