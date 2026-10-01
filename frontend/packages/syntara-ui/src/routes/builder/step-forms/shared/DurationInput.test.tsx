import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { DurationInput } from './DurationInput'

function setup(value: number | undefined, onChange = vi.fn()) {
  const user = userEvent.setup()
  const view = render(<DurationInput value={value} onChange={onChange} idPrefix="test" />)
  return { user, onChange, ...view }
}

describe('DurationInput', () => {
  it('renders four labelled inputs', () => {
    setup(undefined)
    expect(screen.getByRole('spinbutton', { name: 'Days' })).toBeInTheDocument()
    expect(screen.getByRole('spinbutton', { name: 'Hours' })).toBeInTheDocument()
    expect(screen.getByRole('spinbutton', { name: 'Minutes' })).toBeInTheDocument()
    expect(screen.getByRole('spinbutton', { name: 'Seconds' })).toBeInTheDocument()
  })

  it('shows empty inputs when value is undefined', () => {
    setup(undefined)
    expect(screen.getByRole('spinbutton', { name: 'Days' })).toHaveValue(null)
    expect(screen.getByRole('spinbutton', { name: 'Hours' })).toHaveValue(null)
    expect(screen.getByRole('spinbutton', { name: 'Minutes' })).toHaveValue(null)
    expect(screen.getByRole('spinbutton', { name: 'Seconds' })).toHaveValue(null)
  })

  it('shows correct values when given a total seconds value', () => {
    // 1 day + 2 hours + 3 minutes + 4 seconds = 93784 seconds
    setup(93784)
    expect(screen.getByRole('spinbutton', { name: 'Days' })).toHaveValue(1)
    expect(screen.getByRole('spinbutton', { name: 'Hours' })).toHaveValue(2)
    expect(screen.getByRole('spinbutton', { name: 'Minutes' })).toHaveValue(3)
    expect(screen.getByRole('spinbutton', { name: 'Seconds' })).toHaveValue(4)
  })

  it('shows zero for components that are zero when value is set (regression: 0 must not show as empty)', () => {
    // 300 seconds = 5 minutes, 0 seconds/hours/days
    setup(300)
    expect(screen.getByRole('spinbutton', { name: 'Minutes' })).toHaveValue(5)
    expect(screen.getByRole('spinbutton', { name: 'Seconds' })).toHaveValue(0)
    expect(screen.getByRole('spinbutton', { name: 'Hours' })).toHaveValue(0)
    expect(screen.getByRole('spinbutton', { name: 'Days' })).toHaveValue(0)
  })

  it('calls onChange with combined seconds when a field changes', async () => {
    const onChange = vi.fn()
    const { user } = setup(undefined, onChange)
    const hoursInput = screen.getByRole('spinbutton', { name: 'Hours' })
    await user.clear(hoursInput)
    await user.type(hoursInput, '2')
    expect(onChange).toHaveBeenCalledWith(7200) // 2 hours in seconds
  })

  it('calls onChange with undefined when all fields are cleared', async () => {
    const onChange = vi.fn()
    const { user } = setup(3600, onChange)
    const hoursInput = screen.getByRole('spinbutton', { name: 'Hours' })
    await user.clear(hoursInput)
    expect(onChange).toHaveBeenLastCalledWith(undefined)
  })

  it('converts 0 total seconds to all-zero fields', () => {
    setup(0)
    expect(screen.getByRole('spinbutton', { name: 'Days' })).toHaveValue(0)
    expect(screen.getByRole('spinbutton', { name: 'Hours' })).toHaveValue(0)
    expect(screen.getByRole('spinbutton', { name: 'Minutes' })).toHaveValue(0)
    expect(screen.getByRole('spinbutton', { name: 'Seconds' })).toHaveValue(0)
  })

  it('renders disabled inputs when isDisabled is true', () => {
    render(<DurationInput value={300} onChange={vi.fn()} idPrefix="test" isDisabled />)
    expect(screen.getByRole('spinbutton', { name: 'Days' })).toBeDisabled()
    expect(screen.getByRole('spinbutton', { name: 'Hours' })).toBeDisabled()
    expect(screen.getByRole('spinbutton', { name: 'Minutes' })).toBeDisabled()
    expect(screen.getByRole('spinbutton', { name: 'Seconds' })).toBeDisabled()
  })

  it('updates days field correctly', async () => {
    const onChange = vi.fn()
    const { user } = setup(undefined, onChange)
    const daysInput = screen.getByRole('spinbutton', { name: 'Days' })
    await user.clear(daysInput)
    await user.type(daysInput, '2')
    expect(onChange).toHaveBeenCalledWith(172800)
  })

  it('updates seconds field correctly', async () => {
    const onChange = vi.fn()
    const { user } = setup(undefined, onChange)
    const secondsInput = screen.getByRole('spinbutton', { name: 'Seconds' })
    await user.clear(secondsInput)
    await user.type(secondsInput, '5')
    expect(onChange).toHaveBeenLastCalledWith(5)
  })

  it('updates minutes field correctly', async () => {
    const onChange = vi.fn()
    const { user } = setup(undefined, onChange)
    const minutesInput = screen.getByRole('spinbutton', { name: 'Minutes' })
    await user.clear(minutesInput)
    await user.type(minutesInput, '5')
    expect(onChange).toHaveBeenCalledWith(300)
  })

  it('has no accessibility violations', async () => {
    const { container } = setup(3661)
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })
})
