import type { Meta, StoryObj } from '@storybook/tanstack-react'
import { useState } from 'react'
import { fn } from 'storybook/test'

import type { DateValueShape } from '../../forms/dateFieldUtils'

import { FormDateValueInputs } from './FormDateValueInputs'

function DateValueInputsDemo({
  included,
  initialValue,
}: {
  included: Array<'date' | 'time' | 'timezone'>
  initialValue?: DateValueShape | null
}) {
  const [value, setValue] = useState<DateValueShape | null>(initialValue ?? null)

  return (
    <FormDateValueInputs
      included={included}
      value={value}
      onChange={setValue}
      idPrefix="story-date"
      dateAriaLabel="Date"
      timeAriaLabel="Time"
      timezoneAriaLabel="Time zone"
    />
  )
}

const meta: Meta<typeof FormDateValueInputs> = {
  component: FormDateValueInputs,
  tags: ['autodocs'],
  parameters: {
    docs: {
      description: {
        component:
          'Composable date, time, and time zone inputs used by the form field builder and dynamic form responder.',
      },
    },
  },
}
export default meta

type Story = StoryObj<typeof meta>

export const DateOnly: Story = {
  render: () => <DateValueInputsDemo included={['date']} initialValue={{ date: '2026-06-01' }} />,
}

export const DateTimeAndTimezone: Story = {
  render: () => (
    <DateValueInputsDemo
      included={['date', 'time', 'timezone']}
      initialValue={{ date: '2026-06-01', time: '09:30', timezone: 'America/New_York' }}
    />
  ),
}

export const TimezoneOnly: Story = {
  render: () => <DateValueInputsDemo included={['timezone']} initialValue={{ timezone: 'UTC' }} />,
}

export const Interactive: Story = {
  args: {
    onChange: fn(),
  },
  render: () => <DateValueInputsDemo included={['date', 'time', 'timezone']} />,
}
