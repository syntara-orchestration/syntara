import { Label } from '@patternfly/react-core'
import type { Meta, StoryObj } from '@storybook/react-vite'

import { SynDetail } from './SynDetail'

const meta: Meta<typeof SynDetail> = {
  component: SynDetail,
}
export default meta

type Story = StoryObj<typeof meta>

/** A single label/value row as it appears inside a credential or workflow detail page. */
export const Default: Story = {
  args: {
    label: 'Name',
    children: 'prod-aws-credentials',
  },
}

/** Children can be any React node — useful for status badges, labels, or links. */
export const WithJSXChildren: Story = {
  args: {
    label: 'Credential type',
    children: <Label color="blue">Amazon Web Services</Label>,
  },
}

/**
 * When `children` is absent or null the component renders nothing.
 * Optional fields can be passed unconditionally — absent ones are silently skipped.
 */
export const EmptyChildren: Story = {
  args: {
    label: 'Description',
    children: undefined,
  },
}
