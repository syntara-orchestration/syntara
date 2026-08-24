import type { Meta, StoryObj } from '@storybook/react-vite'
import { fn } from 'storybook/test'

import { pageDecorator } from './storyDecorators'
import { SynErrorState } from './SynErrorState'

const meta: Meta<typeof SynErrorState> = {
  component: SynErrorState,
  decorators: [pageDecorator],
  tags: ['autodocs'],
}
export default meta

type Story = StoryObj<typeof meta>

export const Default: Story = {
  args: {
    message: 'Something went wrong while loading the data.',
  },
}

export const WithRetry: Story = {
  args: {
    message: { detail: 'Connection timed out.', retryable: true },
    onRetry: fn(),
  },
}

export const CustomTitle: Story = {
  args: {
    title: 'Workflow not found',
    message: 'The workflow you requested does not exist or has been deleted.',
  },
}
