import type { Meta, StoryObj } from '@storybook/tanstack-react'

import { ReplayedOutputBadge } from './ReplayedOutputBadge'

const meta: Meta<typeof ReplayedOutputBadge> = {
  component: ReplayedOutputBadge,
  tags: ['autodocs'],
  parameters: {
    docs: {
      description: {
        component: 'Marks a step whose output was reused from a previous execution.',
      },
    },
  },
}

export default meta

type Story = StoryObj<typeof meta>

export const Default: Story = {}
