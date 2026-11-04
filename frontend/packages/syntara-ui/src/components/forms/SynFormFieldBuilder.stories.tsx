import type { Meta, StoryObj } from '@storybook/tanstack-react'
import { fn } from 'storybook/test'

import { sampleDynamicFormDefinition } from './dynamicForm/synDynamicFormFixtures'
import { createEmptyFormDefinition } from './formFieldBuilder/createDefaultField'
import { SynFormFieldBuilder } from './SynFormFieldBuilder'

const meta: Meta<typeof SynFormFieldBuilder> = {
  component: SynFormFieldBuilder,
  tags: ['autodocs'],
  parameters: {
    docs: {
      description: {
        component:
          'Visual editor for interactive prompt form definitions. ' +
          'File upload is not available in the builder until it is added to the FormDefinition schema.',
      },
    },
  },
}

export default meta

type Story = StoryObj<typeof SynFormFieldBuilder>

export const Empty: Story = {
  args: {
    value: createEmptyFormDefinition(),
    onChange: fn(),
  },
}

export const SampleDefinition: Story = {
  args: {
    value: sampleDynamicFormDefinition,
    onChange: fn(),
  },
}
