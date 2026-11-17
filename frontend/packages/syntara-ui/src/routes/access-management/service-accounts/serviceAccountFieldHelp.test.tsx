import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import { serviceAccountHelp } from './serviceAccountFieldHelp'
import {
  CREDENTIAL_EXPIRATION_HELP,
  DESCRIPTION_HELP,
  GRACE_PERIOD_HELP,
  NAME_HELP,
} from './serviceAccountFieldHelpText'

describe('serviceAccountHelp', () => {
  it('exposes prebuilt help elements for each service account field', async () => {
    const user = userEvent.setup()
    render(
      <>
        {serviceAccountHelp.name}
        {serviceAccountHelp.description}
        {serviceAccountHelp.credentialExpiration}
        {serviceAccountHelp.gracePeriod}
      </>
    )
    await user.click(screen.getByRole('button', { name: 'More info for Name' }))
    expect(screen.getByText(NAME_HELP)).toBeInTheDocument()

    await user.keyboard('{Escape}')
    await user.click(screen.getByRole('button', { name: 'More info for Description' }))
    expect(screen.getByText(DESCRIPTION_HELP)).toBeInTheDocument()

    await user.keyboard('{Escape}')
    await user.click(screen.getByRole('button', { name: 'More info for Credential expiration date' }))
    expect(screen.getByText(CREDENTIAL_EXPIRATION_HELP)).toBeInTheDocument()

    await user.keyboard('{Escape}')
    await user.click(screen.getByRole('button', { name: 'More info for Current secret grace period' }))
    expect(screen.getByText(GRACE_PERIOD_HELP)).toBeInTheDocument()
  })
})
