import type { Meta, StoryObj } from '@storybook/react-vite'

import { createTestRouter } from '../test/createTestRouter'

import { SynLink } from './SynLink'

const Router = createTestRouter('/')

const meta: Meta<typeof SynLink> = {
  component: SynLink,
  tags: ['autodocs'],
  decorators: [
    (Story) => (
      <Router>
        <Story />
      </Router>
    ),
  ],
  parameters: {
    docs: {
      description: {
        component:
          'A PatternFly-styled inline link that renders as an `<a>` element via TanStack Router, preserving right-click, cmd-click, and middle-click semantics. Uses `Button variant="link" isInline` with a custom `component` so PF handles all styling.',
      },
    },
  },
}
export default meta

type Story = StoryObj<typeof meta>

export const Default: Story = {
  args: {
    to: '/workflows',
    children: 'View workflows',
  },
}

export const WithCustomClassName: Story = {
  name: 'With custom className',
  args: {
    to: '/workflows',
    children: 'Styled link',
    className: 'pf-v6-u-font-weight-bold',
  },
}
