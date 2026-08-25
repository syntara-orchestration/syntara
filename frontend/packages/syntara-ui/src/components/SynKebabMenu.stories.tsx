import { RhUiDuplicateIcon, RhUiEditIcon, RhUiTrashIcon } from '@patternfly/react-icons'
import type { Meta, StoryObj } from '@storybook/react-vite'
import { fn } from 'storybook/test'

import { IconLabel } from './IconLabel'
import type { KebabAction } from './SynKebabMenu'
import { SynKebabMenu } from './SynKebabMenu'

const meta: Meta<typeof SynKebabMenu> = {
  component: SynKebabMenu,
  tags: ['autodocs'],
  decorators: [
    (Story) => (
      <div
        style={{
          minHeight: 250,
          display: 'flex',
          justifyContent: 'flex-end',
          alignItems: 'flex-start',
          padding: 'var(--pf-t--global--spacer--md)',
        }}
      >
        <Story />
      </div>
    ),
  ],
  parameters: {
    docs: {
      description: {
        component:
          'A kebab (three-dot) dropdown menu for row-level or contextual actions.\n\n' +
          'Supports normal items, danger items, separators, disabled items with tooltips, ' +
          'and aria-disabled items that remain focusable for assistive technology.',
      },
    },
  },
  args: {
    'aria-label': 'Actions',
  },
}

export default meta
type Story = StoryObj<typeof SynKebabMenu>

const defaultActions: KebabAction[] = [
  { key: 'edit', title: <IconLabel icon={<RhUiEditIcon />}>Edit</IconLabel>, onClick: fn() },
  { key: 'duplicate', title: <IconLabel icon={<RhUiDuplicateIcon />}>Duplicate</IconLabel>, onClick: fn() },
  { key: 'sep', isSeparator: true },
  { key: 'delete', title: <IconLabel icon={<RhUiTrashIcon />}>Delete</IconLabel>, isDanger: true, onClick: fn() },
]

export const Default: Story = {
  args: { actions: defaultActions },
}

export const WithDisabledItems: Story = {
  args: {
    actions: [
      {
        key: 'edit',
        title: <IconLabel icon={<RhUiEditIcon />}>Edit</IconLabel>,
        isAriaDisabled: true,
        tooltipProps: { content: 'You do not have permission to edit this resource (requires resource:update)' },
      },
      { key: 'sep', isSeparator: true },
      {
        key: 'delete',
        title: <IconLabel icon={<RhUiTrashIcon />}>Delete</IconLabel>,
        isDanger: true,
        isAriaDisabled: true,
        tooltipProps: { content: 'You do not have permission to delete this resource (requires resource:delete)' },
      },
    ],
    'aria-label': 'Actions (disabled)',
  },
}

export const AllEnabled: Story = {
  args: {
    actions: [
      { key: 'edit', title: 'Edit', onClick: fn() },
      { key: 'duplicate', title: 'Duplicate', onClick: fn() },
      { key: 'export', title: 'Export', onClick: fn() },
    ],
    'aria-label': 'Actions (all enabled)',
  },
}
