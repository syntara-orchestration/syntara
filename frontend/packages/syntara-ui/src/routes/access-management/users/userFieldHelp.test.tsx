import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactElement } from 'react'
import { describe, expect, it } from 'vitest'

import { userHelp } from './userFieldHelp'
import {
  EMAIL_CREATE_HELP,
  EMAIL_FEDERATED_EDIT_HELP,
  EMAIL_HELP,
  GROUPS_HELP,
  STATUS_HELP,
  USERNAME_HELP,
} from './userFieldHelpText'

const helpCases: [label: string, element: ReactElement, buttonName: string, expectedText: string][] = [
  ['username', userHelp.username, 'More info for Username', USERNAME_HELP],
  ['email (edit)', userHelp.email, 'More info for Email', EMAIL_HELP],
  ['email (create)', userHelp.emailCreate, 'More info for Email', EMAIL_CREATE_HELP],
  ['email (federated edit)', userHelp.emailFederatedEdit, 'More info for Email', EMAIL_FEDERATED_EDIT_HELP],
  ['groups', userHelp.groups, 'More info for Groups', GROUPS_HELP],
  ['status', userHelp.status, 'More info for Status', STATUS_HELP],
]

describe('userHelp', () => {
  it.each(helpCases)('%s help popover', async (_label, element, buttonName, expectedText) => {
    const user = userEvent.setup()
    render(element)
    await user.click(screen.getByRole('button', { name: buttonName }))
    expect(screen.getByText(expectedText)).toBeInTheDocument()
  })
})
