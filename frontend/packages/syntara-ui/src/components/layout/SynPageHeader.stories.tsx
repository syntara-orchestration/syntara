import { Button, Switch } from '@patternfly/react-core'
import type { Meta, StoryObj } from '@storybook/react-vite'
import { useState } from 'react'

import { NxKebabMenu } from '../NxKebabMenu'

import { SynPageHeader } from './SynPageHeader'

function SwitchToggleHeader() {
  const [enabled, setEnabled] = useState(true)
  return (
    <SynPageHeader
      title="Page title"
      toolbar={
        <Switch
          id="page-header-example-switch"
          label="Enabled"
          isChecked={enabled}
          onChange={(_event, checked) => setEnabled(checked)}
        />
      }
    />
  )
}

const kebabActions = [
  { key: 'edit', title: 'Edit', onClick: () => {} },
  { key: 'duplicate', title: 'Duplicate', onClick: () => {} },
  { key: 'sep', isSeparator: true },
  { key: 'delete', title: 'Delete', isDanger: true, onClick: () => {} },
]

function DetailPageToolbarHeader() {
  const [enabled, setEnabled] = useState(true)
  return (
    <SynPageHeader
      title="my-credential"
      breadcrumbs={[{ label: 'Credentials', href: '/credentials' }, { label: 'my-credential' }]}
      toolbar={
        <>
          <Switch
            id="detail-page-example-switch"
            label="Enabled"
            isChecked={enabled}
            onChange={(_event, checked) => setEnabled(checked)}
          />
          <Button variant="secondary">Edit</Button>
          <NxKebabMenu aria-label="More actions" actions={kebabActions} />
        </>
      }
    />
  )
}

const meta: Meta<typeof SynPageHeader> = {
  component: SynPageHeader,
  tags: ['autodocs'],
  args: {
    title: 'Page title',
  },
  parameters: {
    docs: {
      description: {
        component:
          'Page header with title, optional breadcrumbs, and an optional toolbar slot for page-level actions.\n\n' +
          '**Button placement:** In page headers, the primary action must always be the **rightmost** button. ' +
          'Place secondary buttons to its left. This is the opposite of modals and full-page forms, where the primary button is leftmost.',
      },
    },
  },
}
export default meta

type Story = StoryObj<typeof meta>

export const Default: Story = {
  parameters: {
    docs: { description: { story: 'Title-only header — no breadcrumbs and no toolbar.' } },
  },
}

export const PrimaryAction: Story = {
  name: 'Toolbar — primary action',
  parameters: {
    docs: {
      description: {
        story: 'A single primary action in the toolbar. Typical on list pages where the main action is "Create".',
      },
    },
  },
  args: {
    toolbar: <Button variant="primary">Create workflow</Button>,
  },
}

export const SecondaryAction: Story = {
  name: 'Toolbar — secondary action',
  parameters: {
    docs: {
      description: {
        story:
          'A single secondary action. Typical on detail pages where the only header-level action is an edit or export.',
      },
    },
  },
  args: {
    toolbar: <Button variant="secondary">Edit</Button>,
  },
}

export const WithToolbar: Story = {
  name: 'Toolbar — primary + secondary',
  parameters: {
    docs: {
      description: {
        story: 'Secondary actions appear to the left; the primary action is always rightmost.',
      },
    },
  },
  args: {
    toolbar: (
      <>
        <Button variant="secondary">Export</Button>
        <Button variant="primary">Create</Button>
      </>
    ),
  },
}

export const WithSwitch: Story = {
  name: 'Toolbar — switch',
  parameters: {
    docs: {
      description: {
        story:
          'A switch lets users toggle a resource state (e.g. enabled/disabled) directly from the page header without opening a dialog.',
      },
    },
  },
  render: () => <SwitchToggleHeader />,
}

export const WithKebab: Story = {
  name: 'Toolbar — kebab menu',
  parameters: {
    docs: {
      description: {
        story:
          'A kebab menu groups infrequent or destructive actions that would clutter the toolbar if shown as buttons.',
      },
    },
  },
  args: {
    toolbar: <NxKebabMenu aria-label="More actions" actions={kebabActions} />,
  },
}

export const DetailPageToolbar: Story = {
  name: 'Toolbar — switch + action + kebab (detail page)',
  parameters: {
    docs: {
      description: {
        story:
          'Detail page pattern: a switch for resource state, a secondary action button, and a kebab for overflow actions — all together in the toolbar.',
      },
    },
  },
  render: () => <DetailPageToolbarHeader />,
}

export const WithBreadcrumbs: Story = {
  parameters: {
    docs: {
      description: {
        story:
          'Breadcrumb trail renders above the title. Use on detail and form pages where context helps orient the user.',
      },
    },
  },
  args: {
    title: 'Create user',
    breadcrumbs: [
      { label: 'Access management', href: '/access-management' },
      { label: 'Users', href: '/access-management/users' },
      { label: 'Create user' },
    ],
  },
}

export const WithBreadcrumbsAndToolbar: Story = {
  parameters: {
    docs: {
      description: {
        story: 'The same button order rule applies when breadcrumbs are present: secondary left, primary rightmost.',
      },
    },
  },
  args: {
    title: 'Edit workflow',
    breadcrumbs: [
      { label: 'Automation', href: '/automation' },
      { label: 'Workflows', href: '/automation/workflows' },
      { label: 'Edit workflow' },
    ],
    toolbar: (
      <>
        <Button variant="secondary">Cancel</Button>
        <Button variant="primary">Save</Button>
      </>
    ),
  },
}

export const SingleBreadcrumbHidden: Story = {
  parameters: {
    docs: {
      description: {
        story:
          'A single breadcrumb item is below the two-item threshold — `SynPageBreadcrumbs` renders nothing and only the title shows.',
      },
    },
  },
  args: {
    title: 'Users',
    breadcrumbs: [{ label: 'Access management', href: '/access-management' }],
  },
}
