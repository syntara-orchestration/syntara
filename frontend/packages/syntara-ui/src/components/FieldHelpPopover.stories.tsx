import { FormGroup, TextInput } from '@patternfly/react-core'
import type { Meta, StoryObj } from '@storybook/react-vite'

import { FieldHelpPopover } from './FieldHelpPopover'

const meta: Meta<typeof FieldHelpPopover> = {
  component: FieldHelpPopover,
  tags: ['autodocs'],
  parameters: {
    docs: {
      description: {
        component:
          'Shared RhUi question-mark icon + Popover for form field help. ' +
          'Pass as `labelHelp` on FormGroup. Prefer a string `headerContent` so the trigger ' +
          'aria-label becomes "More info for {header}".',
      },
    },
  },
  decorators: [
    (Story) => (
      <div style={{ padding: 'var(--pf-t--global--spacer--md)', maxWidth: '24rem' }}>
        <Story />
      </div>
    ),
  ],
}

export default meta
type Story = StoryObj<typeof FieldHelpPopover>

export const Default: Story = {
  render: () => (
    <FormGroup
      label="Issuer URL"
      labelHelp={<FieldHelpPopover helpText="The OpenID Connect issuer URL for this identity provider." />}
      fieldId="story-issuer"
    >
      <TextInput id="story-issuer" aria-label="Issuer URL" />
    </FormGroup>
  ),
}

export const WithHeader: Story = {
  render: () => (
    <FormGroup
      label="Input schema"
      labelHelp={
        <FieldHelpPopover
          headerContent="Input schema"
          helpText="Define an input schema to validate data when the workflow starts."
        />
      }
      fieldId="story-schema"
    >
      <TextInput id="story-schema" aria-label="Input schema" />
    </FormGroup>
  ),
}
