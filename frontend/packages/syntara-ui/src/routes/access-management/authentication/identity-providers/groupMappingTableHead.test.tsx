import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { axe } from 'vitest-axe'

import { APP_TITLE } from '../../../../utils/appTitle'

import { GroupMappingTableHead } from './groupMappingTableHead'
import { GROUP_HELP, IDP_GROUP_VALUE_HELP } from './idpFieldHelpText'

describe('GroupMappingTableHead', () => {
  const defaultProps = {
    showActionsColumn: false,
  }

  it('renders column headers with field help', () => {
    render(
      <table>
        <GroupMappingTableHead {...defaultProps} />
      </table>
    )

    expect(screen.getByText('IdP group value')).toBeInTheDocument()
    expect(screen.getByText(`${APP_TITLE} group`)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'More info for IdP group value' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'More info for Group' })).toBeInTheDocument()
  })

  it('does not render Actions column header when showActionsColumn is false', () => {
    render(
      <table>
        <GroupMappingTableHead {...defaultProps} />
      </table>
    )

    expect(screen.queryByText('Actions')).not.toBeInTheDocument()
  })

  it('renders Actions column header when showActionsColumn is true', () => {
    render(
      <table>
        <GroupMappingTableHead {...defaultProps} showActionsColumn />
      </table>
    )

    // Actions column uses screenReaderText prop, so it's present but visually hidden
    const header = screen.getByRole('columnheader', { name: 'Actions' })
    expect(header).toBeInTheDocument()
  })

  it('field help popovers show IdP group value and Group copy', async () => {
    const user = userEvent.setup()
    render(
      <table>
        <GroupMappingTableHead {...defaultProps} />
      </table>
    )

    await user.click(screen.getByRole('button', { name: 'More info for IdP group value' }))
    expect(screen.getByText(IDP_GROUP_VALUE_HELP)).toBeInTheDocument()

    await user.keyboard('{Escape}')
    await user.click(screen.getByRole('button', { name: 'More info for Group' }))
    expect(screen.getByText(GROUP_HELP)).toBeInTheDocument()
  })
  it('has no accessibility violations with actions column', async () => {
    const { container } = render(
      <table>
        <GroupMappingTableHead {...defaultProps} showActionsColumn />
      </table>
    )
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('has no accessibility violations with all features enabled', async () => {
    const { container } = render(
      <table>
        <GroupMappingTableHead showActionsColumn />
      </table>
    )
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })
})
