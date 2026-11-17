import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import type { SynNumberInputEmptyValue } from './SynNumberInputControl'
import { SynNumberInputControl } from './SynNumberInputControl'

function ControlledNumberInput({
  initialValue,
  emptyValue,
}: {
  initialValue: number | SynNumberInputEmptyValue
  emptyValue: SynNumberInputEmptyValue
}) {
  const [value, setValue] = useState<number | SynNumberInputEmptyValue>(initialValue)

  return (
    <SynNumberInputControl
      fieldId="qty"
      ariaLabel="Quantity"
      value={value}
      emptyValue={emptyValue}
      onChange={setValue}
    />
  )
}

describe('SynNumberInputControl', () => {
  it('has no accessibility violations', async () => {
    const { container } = render(
      <SynNumberInputControl fieldId="qty" ariaLabel="Quantity" value={null} emptyValue={null} onChange={vi.fn()} />
    )
    expect(await axe(container)).toHaveNoViolations()
  })

  it('uses increment and decrement controls', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()

    render(
      <SynNumberInputControl fieldId="qty" ariaLabel="Quantity" value={null} emptyValue={null} onChange={onChange} />
    )

    const input = screen.getByRole('spinbutton', { name: 'Quantity' })
    expect(input).toHaveValue(null)

    await user.click(screen.getByRole('button', { name: 'Plus' }))
    expect(onChange).toHaveBeenCalledWith(1)

    await user.click(screen.getByRole('button', { name: 'Minus' }))
    expect(onChange).toHaveBeenLastCalledWith(-1)
  })

  it('stores null when cleared and blurred for definition defaults', async () => {
    const user = userEvent.setup()

    render(<ControlledNumberInput initialValue={5} emptyValue={null} />)

    const input = screen.getByRole('spinbutton', { name: 'Quantity' })
    await user.clear(input)
    await user.tab()

    expect(input).toHaveValue(null)

    await user.click(screen.getByRole('button', { name: 'Plus' }))
    expect(input).toHaveValue(1)
  })

  it('stores empty string when cleared and blurred for submission forms', async () => {
    const user = userEvent.setup()

    render(<ControlledNumberInput initialValue={5} emptyValue="" />)

    const input = screen.getByRole('spinbutton', { name: 'Quantity' })
    await user.clear(input)
    await user.tab()

    expect(input).toHaveValue(null)

    await user.click(screen.getByRole('button', { name: 'Plus' }))
    expect(input).toHaveValue(1)
  })
})
