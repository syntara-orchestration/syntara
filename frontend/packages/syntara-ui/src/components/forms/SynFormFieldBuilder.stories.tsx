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
          'Visual editor for form step form definitions. ' +
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

export const PreviewTabWithPresentationOptions: Story = {
  args: {
    value: sampleDynamicFormDefinition,
    onChange: fn(),
    previewSubmitLabel: 'Start workflow',
    previewCssOverrideSource: '.form-step-response-form label { font-weight: 700; }',
    previewDescription: 'Complete the fields below before continuing.',
  },
  parameters: {
    docs: {
      description: {
        story:
          'Open the Preview tab to see submit label, message, and CSS override applied (same as the builder Preview form modal).',
      },
    },
  },
}
