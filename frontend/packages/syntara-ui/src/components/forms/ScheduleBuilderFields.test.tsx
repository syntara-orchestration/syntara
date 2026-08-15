import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { ScheduleBuilderFields } from './ScheduleBuilderFields'

describe('ScheduleBuilderFields', () => {
  it('renders all schedule fields', () => {
    render(<ScheduleBuilderFields />)

    expect(screen.getByLabelText('Start date')).toBeInTheDocument()
    expect(screen.getByLabelText('Start time')).toBeInTheDocument()
    expect(screen.getByLabelText('End date', { selector: 'input' })).toBeInTheDocument()
    expect(screen.getByLabelText('Frequency')).toBeInTheDocument()
  })

  it('has no accessibility violations', async () => {
    const { container } = render(<ScheduleBuilderFields />)
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('calls onChange when start date is filled', async () => {
    const onChange = vi.fn()
    render(<ScheduleBuilderFields onChange={onChange} />)

    const user = userEvent.setup()
    await user.clear(screen.getByLabelText('Start date'))
    await user.type(screen.getByLabelText('Start date'), '2026-01-15')

    await waitFor(() => {
      expect(onChange).toHaveBeenCalled()
      const lastCall = onChange.mock.calls.at(-1)?.[0] as string
      expect(lastCall).toContain('2026-01-15')
    })
  })

  it('parses existing interval value into fields', () => {
    render(<ScheduleBuilderFields value="R/2024-01-15T10:00:00Z/P1D" />)

    expect(screen.getByLabelText('Start date')).toHaveValue('2024-01-15')
    expect(screen.getByLabelText('Start time')).toHaveValue('10:00 AM')
    expect(screen.getByLabelText('Frequency')).toHaveTextContent('Daily')
  })

  it('parses weekly interval correctly', () => {
    render(<ScheduleBuilderFields value="R/2024-03-01T09:00:00Z/P1W" />)

    expect(screen.getByLabelText('Frequency')).toHaveTextContent('Weekly')
  })

  it('parses interval with end date', () => {
    render(<ScheduleBuilderFields value="R/2024-01-15T10:00:00Z/P1D/2024-12-31T23:59:59Z" />)

    expect(screen.getByLabelText('Start date')).toHaveValue('2024-01-15')
    expect(screen.getByLabelText('End date', { selector: 'input' })).toHaveValue('2024-12-31')
  })

  it('shows interval count field when frequency is not none', () => {
    render(<ScheduleBuilderFields value="R/2024-01-15T10:00:00Z/P1D" />)

    expect(screen.getByLabelText('Interval count')).toBeInTheDocument()
    expect(screen.getByLabelText('Interval count')).toHaveValue(1)
  })

  it('hides interval count field when frequency is none', () => {
    render(<ScheduleBuilderFields value="R1/2024-01-15T10:00:00Z/PT0S" />)

    expect(screen.queryByLabelText('Interval count')).not.toBeInTheDocument()
  })

  it('shows error state with error message', () => {
    render(<ScheduleBuilderFields error errorMessage="Start date is required" />)

    expect(screen.getByText('Start date is required')).toBeInTheDocument()
    expect(screen.getByLabelText('Start date', { selector: 'input' })).toHaveAttribute('aria-invalid', 'true')
    expect(screen.getByLabelText('End date', { selector: 'input' })).not.toHaveAttribute('aria-invalid', 'true')
  })

  it('does not show error message when error is false', () => {
    render(<ScheduleBuilderFields error={false} errorMessage="Start date is required" />)

    expect(screen.queryByText('Start date is required')).not.toBeInTheDocument()
  })

  it('renders required indicators when required prop is set', () => {
    render(<ScheduleBuilderFields required />)

    expect(screen.getByLabelText('Start date')).toHaveAttribute('aria-required', 'true')
  })

  it('renders end date helper text', () => {
    render(<ScheduleBuilderFields />)

    expect(screen.getByText('If this field is left empty, the schedule will not have an end date.')).toBeInTheDocument()
  })

  it('calls onTimezoneChange when timezone is selected', async () => {
    const onTimezoneChange = vi.fn()
    const user = userEvent.setup()
    render(<ScheduleBuilderFields timezone="UTC" onTimezoneChange={onTimezoneChange} />)

    await user.click(screen.getByRole('button', { name: 'UTC' }))
    await user.type(screen.getByPlaceholderText('Filter timezones'), 'America/New_York')
    const option = await screen.findByRole('option', { name: 'America/New_York' })
    await user.click(option)

    expect(onTimezoneChange).toHaveBeenCalledWith('America/New_York')
  })

  it('renders multi-unit interval count', () => {
    render(<ScheduleBuilderFields value="R/2024-01-15T10:00:00Z/P3D" />)

    expect(screen.getByLabelText('Frequency')).toHaveTextContent('Daily')
    expect(screen.getByLabelText('Interval count')).toHaveValue(3)
  })

  it('renders help popover buttons for all fields', () => {
    render(<ScheduleBuilderFields value="R/2024-01-15T10:00:00Z/P1D" />)

    expect(screen.getByRole('button', { name: 'More info for Start date and time' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'More info for End date' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'More info for Frequency' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'More info for Interval' })).toBeInTheDocument()
  })

  it('changes frequency via dropdown', async () => {
    const onChange = vi.fn()
    const user = userEvent.setup()
    render(<ScheduleBuilderFields value="R/2024-01-15T10:00:00Z/P1D" onChange={onChange} />)

    await user.click(screen.getByLabelText('Frequency'))
    await user.click(screen.getByRole('option', { name: 'Weekly' }))

    await waitFor(() => {
      const lastCall = onChange.mock.calls.at(-1)?.[0] as string
      expect(lastCall).toContain('P1W')
    })
  })

  it('increments interval count with plus button', async () => {
    const onChange = vi.fn()
    const user = userEvent.setup()
    render(<ScheduleBuilderFields value="R/2024-01-15T10:00:00Z/P1D" onChange={onChange} />)

    await user.click(screen.getByRole('button', { name: 'Plus' }))

    await waitFor(() => {
      const lastCall = onChange.mock.calls.at(-1)?.[0] as string
      expect(lastCall).toContain('P2D')
    })
  })

  it('decrements interval count with minus button', async () => {
    const onChange = vi.fn()
    const user = userEvent.setup()
    render(<ScheduleBuilderFields value="R/2024-01-15T10:00:00Z/P3D" onChange={onChange} />)

    await user.click(screen.getByRole('button', { name: 'Minus' }))

    await waitFor(() => {
      const lastCall = onChange.mock.calls.at(-1)?.[0] as string
      expect(lastCall).toContain('P2D')
    })
  })

  it('does not decrement interval below 1', async () => {
    const onChange = vi.fn()
    const user = userEvent.setup()
    render(<ScheduleBuilderFields value="R/2024-01-15T10:00:00Z/P1D" onChange={onChange} />)

    await user.click(screen.getByRole('button', { name: 'Minus' }))

    await waitFor(() => {
      expect(screen.getByLabelText('Interval count')).toHaveValue(1)
    })
  })

  it('updates start time', async () => {
    const onChange = vi.fn()
    const user = userEvent.setup()
    render(<ScheduleBuilderFields value="R/2024-01-15T10:00:00Z/P1D" onChange={onChange} />)

    const input = screen.getByLabelText('Start time')
    await user.clear(input)
    await user.paste('2:30 PM')

    await waitFor(() => {
      const lastCall = onChange.mock.calls.at(-1)?.[0] as string
      expect(lastCall).toContain('14:30')
    })
  })

  it('selects a start time from the TimePicker dropdown menu', async () => {
    const onChange = vi.fn()
    const user = userEvent.setup()
    render(<ScheduleBuilderFields value="R/2024-01-15T10:00:00Z/P1D" onChange={onChange} />)

    await user.click(screen.getByLabelText('Start time'))
    await user.click(await screen.findByRole('menuitem', { name: '2:00 PM' }))

    await waitFor(() => {
      const lastCall = onChange.mock.calls.at(-1)?.[0] as string
      expect(lastCall).toContain('14:00')
    })
  })

  it('ignores an incomplete/invalid start time entry', async () => {
    const onChange = vi.fn()
    render(<ScheduleBuilderFields value="R/2024-01-15T10:00:00Z/P1D" onChange={onChange} />)

    await userEvent.setup().type(screen.getByLabelText('Start time'), '9')

    expect(onChange.mock.calls.every((call) => !(call[0] as string).includes('T9:'))).toBe(true)
  })

  it('updates end date', async () => {
    const onChange = vi.fn()
    render(<ScheduleBuilderFields value="R/2024-01-15T10:00:00Z/P1D" onChange={onChange} />)

    await userEvent.setup().type(screen.getByLabelText('End date', { selector: 'input' }), '2024-12-31')

    await waitFor(() => {
      const lastCall = onChange.mock.calls.at(-1)?.[0] as string
      expect(lastCall).toContain('2024-12-31')
    })
  })

  it('clears end date when input is emptied', async () => {
    const onChange = vi.fn()
    render(<ScheduleBuilderFields value="R/2024-01-15T10:00:00Z/P1D/2024-12-31T23:59:59Z" onChange={onChange} />)

    expect(screen.getByLabelText('End date', { selector: 'input' })).toHaveValue('2024-12-31')

    await userEvent.setup().clear(screen.getByLabelText('End date', { selector: 'input' }))

    await waitFor(() => {
      const lastCall = onChange.mock.calls.at(-1)?.[0] as string
      expect(lastCall).not.toContain('2024-12-31')
      expect(lastCall).toMatch(/^R\/2024-01-15T10:00:00\+00:00\/P1D$/)
    })
  })

  it('shows error when end date is before start date', () => {
    render(<ScheduleBuilderFields value="R/2024-06-15T10:00:00Z/P1D/2024-06-01T23:59:59Z" />)

    expect(screen.getByText('End date must be on or after the start date.')).toBeInTheDocument()
    expect(screen.getByLabelText('End date', { selector: 'input' })).toHaveAttribute('aria-invalid', 'true')
    expect(screen.getByLabelText('Start date', { selector: 'input' })).not.toHaveAttribute('aria-invalid', 'true')
  })

  it('does not show end date error when end date is after start date', () => {
    render(<ScheduleBuilderFields value="R/2024-01-15T10:00:00Z/P1D/2024-12-31T23:59:59Z" />)

    expect(screen.queryByText('End date must be on or after the start date.')).not.toBeInTheDocument()
    expect(screen.getByLabelText('End date', { selector: 'input' })).not.toHaveAttribute('aria-invalid', 'true')
  })

  it('does not show end date error when end date is empty', () => {
    render(<ScheduleBuilderFields value="R/2024-01-15T10:00:00Z/P1D" />)

    expect(screen.queryByText('End date must be on or after the start date.')).not.toBeInTheDocument()
    expect(screen.getByText('If this field is left empty, the schedule will not have an end date.')).toBeInTheDocument()
  })

  it('calls onChange with a non-empty interval when no start date is set', async () => {
    const onChange = vi.fn()
    render(<ScheduleBuilderFields onChange={onChange} />)

    await waitFor(() => {
      expect(onChange).toHaveBeenCalled()
      expect(onChange.mock.calls.at(-1)?.[0]).toMatch(/^R1\/\d{4}-\d{2}-\d{2}/)
    })
  })

  it('has no accessibility violations when end date is invalid', async () => {
    const { container } = render(<ScheduleBuilderFields value="R/2024-06-15T10:00:00Z/P1D/2024-06-01T23:59:59Z" />)
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })
})
