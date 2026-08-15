import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import { HelpPopover } from './HelpPopover'

describe('HelpPopover', () => {
  it('opens popover with header and body when help control is clicked', async () => {
    const user = userEvent.setup()

    render(
      <HelpPopover ariaLabel="Group help" headerContent="Group" bodyContent="Combine multiple rules with AND or OR." />
    )

    await user.click(screen.getByRole('button', { name: 'Group help' }))

    expect(screen.getByText('Group')).toBeInTheDocument()
    expect(screen.getByText('Combine multiple rules with AND or OR.')).toBeInTheDocument()
  })
})
