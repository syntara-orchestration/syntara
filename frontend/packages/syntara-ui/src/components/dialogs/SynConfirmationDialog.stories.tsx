import { Content } from '@patternfly/react-core'
import type { Meta, StoryObj } from '@storybook/react-vite'
import { fn } from 'storybook/test'

import { SynConfirmationDialog } from './SynConfirmationDialog'

const meta: Meta<typeof SynConfirmationDialog> = {
  component: SynConfirmationDialog,
  tags: ['autodocs'],
  parameters: {
    docs: {
      story: {
        inline: false,
        iframeHeight: '500px',
      },
      description: {
        component:
          'Reusable confirmation dialog for destructive or important actions. ' +
          'Wraps the PF `Modal` + header + body + footer boilerplate into a single component.\n\n' +
          '**Three-tier severity pattern:**\n' +
          '- **Default** — reversible or low-risk actions (e.g., disable); primary confirm button, no title icon.\n' +
          '- **Danger** — reversible but risky actions (remove, unassign, cancel, stop); `confirmVariant="danger"` + `titleIconVariant="warning"`, no checkbox.\n' +
          '- **DestructiveAcknowledgement** — permanent unrecoverable actions (delete); danger confirm button + warning icon + checkbox the user must tick.\n\n' +
          "Wire `confirmLoading` to a mutation's `isPending` flag to prevent double-submit.",
      },
    },
  },
  args: {
    isOpen: true,
    title: 'Confirm action',
    onClose: fn(),
    onConfirm: fn(),
    children: <Content component="p">Are you sure you want to proceed?</Content>,
  },
}
export default meta

type Story = StoryObj<typeof meta>

/** Low-risk or reversible action — primary confirm button, no title icon. Escalate to `Danger` or `DestructiveAcknowledgement` for risky or permanent actions. */
export const Default: Story = {}

/** Non-destructive state change (disable) — primary confirm button, no title icon, no checkbox. Re-enabling is always possible. */
export const Disable: Story = {
  args: {
    title: 'Disable credential?',
    confirmLabel: 'Disable',
    children: (
      <Content component="p">
        You are about to disable the credential <strong>my-aws-key</strong>. You can re-enable it at any time.
      </Content>
    ),
  },
}

/** Reversible but risky action (remove, unassign, cancel, stop) — danger confirm button and warning title icon, no acknowledgement checkbox. */
export const Danger: Story = {
  args: {
    title: 'Remove assignment?',
    confirmLabel: 'Remove',
    confirmVariant: 'danger',
    titleIconVariant: 'warning',
    children: (
      <Content component="p">
        This unassigns the role <strong>Workflow Editor</strong> from this user. Related permissions will be revoked.
      </Content>
    ),
  },
}

/** Permanent unrecoverable action — adds a checkbox the user must tick before confirming. */
export const DestructiveAcknowledgement: Story = {
  args: {
    title: 'Delete workflow?',
    confirmLabel: 'Delete',
    confirmVariant: 'danger',
    titleIconVariant: 'warning',
    destructiveAcknowledgement: {
      checkboxId: 'delete-ack',
      label: 'I understand this workflow will be permanently deleted.',
    },
    children: <Content component="p">This workflow will be permanently deleted. This action cannot be undone.</Content>,
  },
}

/** Confirm button shows a spinner and both buttons are disabled while `confirmLoading` is true. */
export const Loading: Story = {
  args: {
    confirmLoading: true,
  },
}
