import type { Meta, StoryObj } from '@storybook/react-vite'
import { fn } from 'storybook/test'

import { pageDecorator } from './storyDecorators'
import { SynEmptyStateFilter } from './SynEmptyStateFilter'

const meta: Meta<typeof SynEmptyStateFilter> = {
  component: SynEmptyStateFilter,
  decorators: [pageDecorator],
  tags: ['autodocs'],
}
export default meta

type Story = StoryObj<typeof meta>

export const Default: Story = {}

export const WithClearFilters: Story = {
  args: {
    clearAllFilters: fn(),
  },
}

export const CustomText: Story = {
  args: {
    title: 'No matching workflows',
    description: 'No workflows match your current search. Try adjusting your filters.',
    buttonText: 'Reset filters',
    clearAllFilters: fn(),
  },
}
