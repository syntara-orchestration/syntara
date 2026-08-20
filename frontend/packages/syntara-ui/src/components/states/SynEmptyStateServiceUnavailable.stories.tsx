import type { Meta, StoryObj } from '@storybook/react-vite'

import { pageDecorator } from './storyDecorators'
import { SynEmptyStateServiceUnavailable } from './SynEmptyStateServiceUnavailable'

const meta: Meta<typeof SynEmptyStateServiceUnavailable> = {
  component: SynEmptyStateServiceUnavailable,
  decorators: [pageDecorator],
  tags: ['autodocs'],
}
export default meta

type Story = StoryObj<typeof meta>

export const Default: Story = {}

export const CustomDescription: Story = {
  args: {
    description: 'The AI service API key is not configured.',
  },
}

export const WithoutAdminHint: Story = {
  args: {
    description: 'The service is temporarily unavailable.',
    showAdminHint: false,
  },
}
