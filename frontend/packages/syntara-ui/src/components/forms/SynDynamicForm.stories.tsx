import type { Meta, StoryObj } from '@storybook/tanstack-react'
import { fn } from 'storybook/test'

import { invalidDynamicFormDefinition, sampleDynamicFormDefinition } from './dynamicForm/synDynamicFormFixtures'
import { SynDynamicForm } from './SynDynamicForm'

const meta: Meta<typeof SynDynamicForm> = {
  component: SynDynamicForm,
  tags: ['autodocs'],
  parameters: {
    docs: {
      description: {
        component: 'Schema-driven form renderer for interactive prompts. File upload support is deferred.',
      },
    },
  },
}

export default meta

type Story = StoryObj<typeof SynDynamicForm>

export const AllFieldTypes: Story = {
  args: {
    definition: sampleDynamicFormDefinition,
    description: 'Complete this form to continue the workflow.',
    submitLabel: 'Submit response',
    onSubmit: fn(),
    resolveDynamicOptions: () =>
      Promise.resolve([
        { label: 'US East', value: 'use1' },
        { label: 'EU West', value: 'euw1' },
      ]),
  },
}

export const PreviewMode: Story = {
  args: {
    definition: sampleDynamicFormDefinition,
    isReadOnly: true,
    hideSubmitButton: true,
    onSubmit: fn(),
  },
}

export const InvalidConfiguration: Story = {
  args: {
    definition: invalidDynamicFormDefinition,
    onSubmit: fn(),
  },
}
