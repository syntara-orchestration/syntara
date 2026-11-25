import type { Meta, StoryObj } from '@storybook/tanstack-react'
import { createRootRoute, createRoute } from '@tanstack/react-router'
import { fn } from 'storybook/test'

import { SynFormCancelButton } from './SynFormCancelButton'

const rootRoute = createRootRoute()
const mockRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '$',
})

const meta: Meta<typeof SynFormCancelButton> = {
  component: SynFormCancelButton,
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
          'Cancel control for full-page forms and wizard footers. Uses PatternFly link styling and renders ' +
          '`SynLink` when `to` is set.',
      },
    },
  },
}
export default meta

type Story = StoryObj<typeof meta>

export const WithOnClick: Story = {
  args: {
    onClick: fn(),
  },
}

export const WithRoute: Story = {
  args: {
    to: '/users',
  },
}

export const DisabledOnClick: Story = {
  args: {
    onClick: fn(),
    isDisabled: true,
  },
}

export const DisabledWithRoute: Story = {
  args: {
    to: '/users',
    isDisabled: true,
  },
}
