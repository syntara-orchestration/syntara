import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { FormTimezoneSelect } from './FormTimezoneSelect'

describe('FormTimezoneSelect', () => {
  it('renders timezone select toggle', () => {
    render(<FormTimezoneSelect id="tz-select" value="America/New_York" onChange={vi.fn()} ariaLabel="Time zone" />)

    expect(screen.getByRole('button', { name: 'Time zone' })).toHaveTextContent('America/New_York')
  })

  it('has no accessibility violations', async () => {
    const { container } = render(
      <FormTimezoneSelect id="tz-select" value="" onChange={vi.fn()} ariaLabel="Time zone" />
    )

    expect(await axe(container)).toHaveNoViolations()
  })
})
