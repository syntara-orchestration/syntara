import type { Meta, StoryObj } from '@storybook/react-vite'
import { fn } from 'storybook/test'

import { NxEmptyStateViewportTooSmall } from './NxEmptyStateViewportTooSmall'

const meta = {
  title: 'Components/States/NxEmptyStateViewportTooSmall',
  component: NxEmptyStateViewportTooSmall,
  parameters: {
    layout: 'fullscreen',
    docs: {
      description: {
        component:
          'Full-height empty state displayed when the viewport width is below the minimum required for React Flow canvases (1024px). Used by `SynReactFlowViewportGuard` to prevent users from attempting to use the workflow builder or execution visualizer on screens that are too small.',
      },
    },
  },
  tags: ['autodocs'],
  args: {
    onReturn: fn(),
  },
} satisfies Meta<typeof NxEmptyStateViewportTooSmall>

export default meta
type Story = StoryObj<typeof meta>

/**
 * Default viewport too small empty state, shown when screen width < 1024px
 */
export const Default: Story = {}

/**
 * The empty state at its minimum supported width (1024px)
 */
export const AtMinimumViewport: Story = {
  parameters: {
    viewport: {
      defaultViewport: 'mobile2',
    },
  },
}

/**
 * The empty state on a very small mobile viewport
 */
export const MobileViewport: Story = {
  parameters: {
    viewport: {
      defaultViewport: 'mobile1',
    },
  },
}
