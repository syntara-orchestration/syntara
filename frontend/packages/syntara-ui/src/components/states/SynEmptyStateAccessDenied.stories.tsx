import type { Meta, StoryObj } from '@storybook/react-vite'

import { pageDecorator } from './storyDecorators'
import { SynEmptyStateAccessDenied } from './SynEmptyStateAccessDenied'

const meta: Meta<typeof SynEmptyStateAccessDenied> = {
  component: SynEmptyStateAccessDenied,
  decorators: [pageDecorator],
  tags: ['autodocs'],
}
export default meta

type Story = StoryObj<typeof meta>

export const Default: Story = {
  args: {
    description: "You don't have permission to view settings. Contact your administrator to request access.",
  },
}

export const CustomDescription: Story = {
  args: {
    description: "You don't have permission to view access management. Contact your administrator to request access.",
  },
}
