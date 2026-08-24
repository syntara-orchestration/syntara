import type { Meta, StoryObj } from '@storybook/react-vite'

import { pageDecorator } from './storyDecorators'
import { SynLoadingState } from './SynLoadingState'

const meta: Meta<typeof SynLoadingState> = {
  component: SynLoadingState,
  decorators: [pageDecorator],
  tags: ['autodocs'],
}
export default meta

type Story = StoryObj<typeof meta>

export const Default: Story = {}
