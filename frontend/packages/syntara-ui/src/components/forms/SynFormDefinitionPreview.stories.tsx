import type { Meta, StoryObj } from '@storybook/tanstack-react'

import { FormFieldTypeEnum, parseFormDefinition } from '../../forms'

import { sampleDynamicFormDefinition } from './dynamicForm/synDynamicFormFixtures'
import { SynFormDefinitionPreview } from './SynFormDefinitionPreview'

const meta: Meta<typeof SynFormDefinitionPreview> = {
  component: SynFormDefinitionPreview,
  tags: ['autodocs'],
  parameters: {
    docs: {
      description: {
        component:
          'Read-only builder preview of a form definition, including disabled submit and workflow CSS override.',
      },
    },
  },
}

export default meta

type Story = StoryObj<typeof SynFormDefinitionPreview>

export const Default: Story = {
  args: {
    definition: sampleDynamicFormDefinition,
    description: 'Preview of the configured form.',
    submitLabel: 'Send request',
  },
}

export const WithCssOverride: Story = {
  args: {
    definition: parseFormDefinition({
      fields: [{ type: FormFieldTypeEnum.TEXT, value_name: 'note', label: 'Note' }],
    }),
    description: 'Custom styling applies to labels below.',
    submitLabel: 'Submit',
    cssOverrideSource: '.form-step-response-form label { color: rgb(170, 0, 0) !important; font-weight: 700; }',
  },
}
