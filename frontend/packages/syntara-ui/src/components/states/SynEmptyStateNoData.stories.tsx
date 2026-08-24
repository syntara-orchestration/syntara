import { Button } from '@patternfly/react-core'
import type { Meta, StoryObj } from '@storybook/react-vite'
import { fn } from 'storybook/test'

import { pageDecorator } from './storyDecorators'
import { SynEmptyStateNoData } from './SynEmptyStateNoData'

const meta: Meta<typeof SynEmptyStateNoData> = {
  component: SynEmptyStateNoData,
  decorators: [pageDecorator],
  tags: ['autodocs'],
}
export default meta

type Story = StoryObj<typeof meta>

export const Default: Story = {}

export const WithAction: Story = {
  args: {
    title: 'No workflows found',
    description: 'Create your first workflow to get started.',
    buttonText: 'Create workflow',
    addData: fn(),
  },
}

export const WithSecondaryActions: Story = {
  args: {
    title: 'No credentials configured',
    description: 'Add credentials to connect to external services.',
    buttonText: 'Add credential',
    addData: fn(),
    secondaryActions: <Button variant="link">Learn more</Button>,
  },
}

export const WithCustomImage: Story = {
  args: {
    title: 'No executions yet',
    description: 'Run a workflow to see executions here.',
    imageSrc:
      "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='200' height='150' viewBox='0 0 200 150'%3E%3Crect width='200' height='150' rx='8' fill='%23f0f0f0'/%3E%3Ctext x='50%25' y='50%25' dominant-baseline='middle' text-anchor='middle' font-family='sans-serif' font-size='14' fill='%23999'%3ENo Data%3C/text%3E%3C/svg%3E",
    imageAlt: 'No executions illustration',
  },
}
