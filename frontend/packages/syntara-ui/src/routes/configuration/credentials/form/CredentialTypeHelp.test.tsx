import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { axe } from 'vitest-axe'

import { CREDENTIAL_TYPE_HELP } from './CredentialTypeHelp'

describe('CredentialTypeHelp', () => {
  it('describes the connection modes that need Kafka login fields', () => {
    render(CREDENTIAL_TYPE_HELP)

    expect(screen.getByText(/SASL_SSL requires a username and password/)).toBeInTheDocument()
  })

  it('has no accessibility violations', async () => {
    const { container } = render(CREDENTIAL_TYPE_HELP)

    expect(await axe(container)).toHaveNoViolations()
  })
})
