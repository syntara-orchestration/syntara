import type { Meta, StoryObj } from '@storybook/react-vite'

import { SynLoadingState } from './SynLoadingState'
import { pageDecorator } from './storyDecorators'

const meta: Meta<typeof SynLoadingState> = {
  component: SynLoadingState,
  decorators: [pageDecorator],
  tags: ['autodocs'],
}
export default meta

type Story = StoryObj<typeof meta>

export const Default: Story = {}
