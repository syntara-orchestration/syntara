import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
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

describe('userHelp', () => {
  it('exposes prebuilt help elements for each user form field', async () => {
    const user = userEvent.setup()
    render(
      <>
        {userHelp.username}
        {userHelp.email}
        {userHelp.emailCreate}
        {userHelp.emailFederatedEdit}
        {userHelp.groups}
        {userHelp.status}
      </>
    )

    await user.click(screen.getByRole('button', { name: 'More info for Username' }))
    expect(screen.getByText(USERNAME_HELP)).toBeInTheDocument()

    await user.keyboard('{Escape}')
    await user.click(screen.getAllByRole('button', { name: 'More info for Email' })[0])
    expect(screen.getByText(EMAIL_HELP)).toBeInTheDocument()

    await user.keyboard('{Escape}')
    await user.click(screen.getAllByRole('button', { name: 'More info for Email' })[1])
    expect(screen.getByText(EMAIL_CREATE_HELP)).toBeInTheDocument()

    await user.keyboard('{Escape}')
    await user.click(screen.getAllByRole('button', { name: 'More info for Email' })[2])
    expect(screen.getByText(EMAIL_FEDERATED_EDIT_HELP)).toBeInTheDocument()

    await user.keyboard('{Escape}')
    await user.click(screen.getByRole('button', { name: 'More info for Groups' }))
    expect(screen.getByText(GROUPS_HELP)).toBeInTheDocument()

    await user.keyboard('{Escape}')
    await user.click(screen.getByRole('button', { name: 'More info for Status' }))
    expect(screen.getByText(STATUS_HELP)).toBeInTheDocument()
  })
})
