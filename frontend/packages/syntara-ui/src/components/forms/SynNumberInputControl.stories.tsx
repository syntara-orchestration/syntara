import { FormGroup } from '@patternfly/react-core'
import type { Meta, StoryObj } from '@storybook/tanstack-react'
import { useState } from 'react'
import { fn } from 'storybook/test'

import type { SynNumberInputEmptyValue } from './SynNumberInputControl'
import { SynNumberInputControl } from './SynNumberInputControl'

function NumberInputControlDemo({
  ariaLabel = 'Quantity',
  emptyValue = null,
  initialValue = null,
  isDisabled,
  placeholder,
  validated = 'default',
}: {
  ariaLabel?: string
  emptyValue?: SynNumberInputEmptyValue
  initialValue?: number | SynNumberInputEmptyValue | null
  isDisabled?: boolean
  placeholder?: string
  validated?: 'default' | 'warning' | 'success' | 'error'
}) {
  const [value, setValue] = useState<number | SynNumberInputEmptyValue | null>(initialValue)

  return (
    <FormGroup label={ariaLabel} fieldId="story-number-input">
      <SynNumberInputControl
        fieldId="story-number-input"
        ariaLabel={ariaLabel}
        value={value}
        emptyValue={emptyValue}
        onChange={setValue}
        isDisabled={isDisabled}
        placeholder={placeholder}
        validated={validated}
      />
    </FormGroup>
  )
}

const meta: Meta<typeof SynNumberInputControl> = {
  component: SynNumberInputControl,
  tags: ['autodocs'],
  parameters: {
    docs: {
      description: {
        component:
          'PatternFly number input (minus, value, plus) shared by dynamic form responders and form field builder initial answers.',
      },
    },
  },
}
export default meta

type Story = StoryObj<typeof meta>

export const Default: Story = {
  render: () => <NumberInputControlDemo />,
}

export const WithValue: Story = {
  render: () => <NumberInputControlDemo initialValue={42} />,
}

export const WithPlaceholder: Story = {
  render: () => <NumberInputControlDemo placeholder="e.g. 10" />,
}

export const Disabled: Story = {
  render: () => <NumberInputControlDemo initialValue={3} isDisabled />,
}

export const Error: Story = {
  render: () => <NumberInputControlDemo initialValue={0} validated="error" />,
}

export const SubmissionEmptyValue: Story = {
  render: () => <NumberInputControlDemo emptyValue="" initialValue="" ariaLabel="Count" />,
}

export const Interactive: Story = {
  args: {
    onChange: fn(),
  },
  render: () => <NumberInputControlDemo placeholder="Type or use plus/minus" />,
}
