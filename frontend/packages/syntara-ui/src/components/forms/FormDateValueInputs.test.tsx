import { render, screen } from '@testing-library/react'
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
})
