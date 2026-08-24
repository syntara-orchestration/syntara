import type { Meta, StoryObj } from '@storybook/react-vite'

import { SynPageBreadcrumbs } from './SynPageBreadcrumbs'

const meta: Meta<typeof SynPageBreadcrumbs> = {
  component: SynPageBreadcrumbs,
  tags: ['autodocs'],
  parameters: {
    docs: {
      description: {
        component:
          'Breadcrumb trail where parent items are links and the last item is the current page (non-interactive).\n\n' +
          'Renders nothing when fewer than two `items` are supplied — a single-item trail provides no navigational value. ' +
          'On narrow viewports (≤768 px), two or more middle segments collapse into a dropdown to keep the trail scannable.',
      },
    },
  },
}
export default meta

type Story = StoryObj<typeof meta>

export const ThreeItems: Story = {
  parameters: {
    docs: { description: { story: 'Typical use — two navigable parent links followed by the current page label.' } },
  },
  args: {
    items: [
      { label: 'Access management', href: '/access-management' },
      { label: 'Users', href: '/access-management/users' },
      { label: 'Create user' },
    ],
  },
}

export const TwoItems: Story = {
  parameters: {
    docs: { description: { story: 'Minimum visible trail — one parent link and the current page label.' } },
  },
  args: {
    items: [{ label: 'Access management', href: '/access-management' }, { label: 'Users' }],
  },
}

export const SingleItemHidden: Story = {
  parameters: {
    docs: {
      description: { story: 'A single item is below the two-item threshold — the component renders nothing.' },
    },
  },
  args: {
    items: [{ label: 'Access management', href: '/access-management' }],
  },
}

export const ManyItems: Story = {
  parameters: {
    docs: {
      description: {
        story: 'Five-item trail. On narrow viewports (≤768 px) the three middle segments collapse into a dropdown.',
      },
    },
  },
  args: {
    items: [
      { label: 'Settings', href: '/settings' },
      { label: 'Infrastructure', href: '/settings/infrastructure' },
      { label: 'Clusters', href: '/settings/infrastructure/clusters' },
      { label: 'Regions', href: '/settings/infrastructure/clusters/regions' },
      { label: 'Add region' },
    ],
  },
}
