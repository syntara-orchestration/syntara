import { Label } from '@patternfly/react-core'
import type { Meta, StoryObj } from '@storybook/react-vite'

import { SynDetail } from './SynDetail'
import { SynDetailList } from './SynDetailList'

const meta: Meta<typeof SynDetailList> = {
  component: SynDetailList,
}
export default meta

type Story = StoryObj<typeof meta>

/** Vertical detail list — the default layout for credential and workflow detail pages. */
export const Default: Story = {
  render: () => (
    <SynDetailList>
      <SynDetail label="Name">prod-aws-credentials</SynDetail>
      <SynDetail label="Credential type">
        <Label color="blue">Amazon Web Services</Label>
      </SynDetail>
      <SynDetail label="Created by">admin</SynDetail>
      <SynDetail label="Last modified">Nov 15, 2024</SynDetail>
    </SynDetailList>
  ),
}

/**
 * `isHorizontal` places the term and description side-by-side.
 * Used inside compact spaces such as workflow canvas step cards.
 */
export const Horizontal: Story = {
  render: () => (
    <SynDetailList isHorizontal>
      <SynDetail label="Name">prod-aws-credentials</SynDetail>
      <SynDetail label="Credential type">
        <Label color="blue">Amazon Web Services</Label>
      </SynDetail>
      <SynDetail label="Created by">admin</SynDetail>
    </SynDetailList>
  ),
}

/**
 * Optional fields can be passed unconditionally — `SynDetail` renders nothing when its value
 * is absent, so the list stays clean without conditional JSX at the call site.
 */
export const WithOptionalFields: Story = {
  render: () => (
    <SynDetailList>
      <SynDetail label="Name">prod-aws-credentials</SynDetail>
      <SynDetail label="Description">{undefined}</SynDetail>
      <SynDetail label="Credential type">
        <Label color="blue">Amazon Web Services</Label>
      </SynDetail>
      <SynDetail label="Last modified">Nov 15, 2024</SynDetail>
    </SynDetailList>
  ),
}
