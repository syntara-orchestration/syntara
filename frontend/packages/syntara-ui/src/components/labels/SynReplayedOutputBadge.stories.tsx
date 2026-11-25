import type { Meta, StoryObj } from '@storybook/tanstack-react'

import { SynReplayedOutputBadge } from './SynReplayedOutputBadge'

const meta: Meta<typeof SynReplayedOutputBadge> = {
  component: SynReplayedOutputBadge,
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
