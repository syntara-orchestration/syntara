import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { FormDateValueInputs } from './FormDateValueInputs'

describe('FormDateValueInputs', () => {
  it('renders date input when date is included', () => {
    render(
      <FormDateValueInputs
        included={['date']}
        value={null}
        onChange={vi.fn()}
        idPrefix="test"
        dateAriaLabel="Due date"
      />
    )

    expect(screen.getByRole('textbox', { name: 'Due date' })).toBeInTheDocument()
  })

  it('has no accessibility violations for date and time', async () => {
    const { container } = render(
      <FormDateValueInputs
        included={['date', 'time']}
        value={{ date: '2026-03-15', time: '14:30' }}
        onChange={vi.fn()}
        idPrefix="test"
        dateAriaLabel="Due date"
        timeAriaLabel="Due time"
      />
    )

    expect(await axe(container)).toHaveNoViolations()
  })

  it('does not call onBlur when focus moves between date and time', async () => {
    const user = userEvent.setup()
    const onBlur = vi.fn()

    render(
      <FormDateValueInputs
        included={['date', 'time']}
        value={{ date: '2026-03-15' }}
        onChange={vi.fn()}
        onBlur={onBlur}
        idPrefix="test"
        dateAriaLabel="Due date"
        timeAriaLabel="Due time"
      />
    )

    await user.click(screen.getByRole('textbox', { name: 'Due date' }))
    await user.click(screen.getByRole('textbox', { name: 'Due time' }))

    expect(screen.getByRole('textbox', { name: 'Due time' })).toHaveFocus()
    expect(onBlur).not.toHaveBeenCalled()
  })

  it('removes a cleared time while preserving the other components', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()

    render(
      <FormDateValueInputs
        included={['date', 'time', 'timezone']}
        value={{ date: '2026-03-15', time: '14:30', timezone: 'America/New_York' }}
        onChange={onChange}
        idPrefix="test"
        dateAriaLabel="Due date"
        timeAriaLabel="Due time"
      />
    )

    await user.clear(screen.getByRole('textbox', { name: 'Due time' }))

    expect(onChange).toHaveBeenCalledWith({ date: '2026-03-15', timezone: 'America/New_York' })
  })
})
