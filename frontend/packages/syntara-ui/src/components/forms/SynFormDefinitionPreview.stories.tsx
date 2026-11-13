import type { Meta, StoryObj } from '@storybook/tanstack-react'

import { sampleDynamicFormDefinition } from './dynamicForm/synDynamicFormFixtures'
import { SynFormDefinitionPreview } from './SynFormDefinitionPreview'

const meta: Meta<typeof SynFormDefinitionPreview> = {
  component: SynFormDefinitionPreview,
  tags: ['autodocs'],
  parameters: {
    docs: {
      description: {
        component: 'Read-only builder preview of a form definition, including disabled submit.',
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
