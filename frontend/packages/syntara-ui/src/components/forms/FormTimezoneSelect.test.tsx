import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { FormTimezoneSelect } from './FormTimezoneSelect'

describe('FormTimezoneSelect', () => {
  it('renders the selected timezone in the typeahead input', () => {
    render(<FormTimezoneSelect id="tz-select" value="America/New_York" onChange={vi.fn()} ariaLabel="Time zone" />)

    expect(screen.getByRole('textbox', { name: 'Time zone' })).toHaveValue('America/New_York')
    expect(screen.getByRole('button', { name: 'Clear time zone' })).toBeInTheDocument()
  })

  it('clears the typeahead filter when the select closes', async () => {
    const user = userEvent.setup()
    render(<FormTimezoneSelect id="tz-select" value="" onChange={vi.fn()} ariaLabel="Time zone" />)

    const input = screen.getByRole('textbox', { name: 'Time zone' })
    await user.click(input)
    await user.type(input, 'America/')

    expect(input).toHaveValue('America/')
    expect(screen.getByRole('listbox')).toBeInTheDocument()

    await user.keyboard('{Escape}')
    await waitFor(() => {
      expect(screen.queryByRole('listbox')).not.toBeInTheDocument()
    })

    await user.click(input)
    expect(input).toHaveValue('')
  })

  it('has no accessibility violations', async () => {
    const { container } = render(
      <FormTimezoneSelect id="tz-select" value="" onChange={vi.fn()} ariaLabel="Time zone" />
    )

    expect(await axe(container)).toHaveNoViolations()
  })
})
