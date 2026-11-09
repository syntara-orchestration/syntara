import type { Meta, StoryObj } from '@storybook/tanstack-react'
import { createRootRoute, createRoute } from '@tanstack/react-router'

import * as routeRefs from '../app/routes/routeReferences'

import { SynLink } from './SynLink'

const workflowsDestination = { to: routeRefs.workflowsRoute.fullPath }

// Wildcard route allows target paths like /workflows to match without router errors
const rootRoute = createRootRoute()
const mockRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '$',
})

const meta: Meta<typeof SynLink> = {
  component: SynLink,
  tags: ['autodocs'],
  parameters: {
    tanstack: {
      router: {
        route: mockRoute,
      },
    },
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
    options: workflowsDestination,
    children: 'View workflows',
  },
}

export const WithCustomClassName: Story = {
  name: 'With custom className',
  args: {
    options: workflowsDestination,
    children: 'Styled link',
    className: 'pf-v6-u-font-weight-bold',
  },
}
