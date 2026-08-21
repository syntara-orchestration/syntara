import type { Meta, StoryObj } from '@storybook/react-vite'
import { expect } from 'storybook/test'

import { toPageTitle } from '../utils/toPageTitle'

import { SynPageTitle } from './SynPageTitle'

const meta: Meta<typeof SynPageTitle> = {
  component: SynPageTitle,
  tags: ['autodocs'],
  parameters: {
    docs: {
      description: {
        component:
          'Sets the browser `<title>` for the current page. Segments are joined with `" | "` and the app name is appended automatically. Null, undefined, and blank segments are filtered out. Place as the first child of `<SynPage>`.',
      },
    },
  },
}
export default meta

type Story = StoryObj<typeof meta>

export const SingleSegment: Story = {
  name: 'Single page segment',
  args: { segments: ['Workflows'] },
  play: async () => {
    await expect(document.title).toBe(toPageTitle(['Workflows']))
  },
}

export const MultipleSegments: Story = {
  name: 'Detail page — item + section',
  args: { segments: ['My Workflow', 'Workflows'] },
  play: async () => {
    await expect(document.title).toBe(toPageTitle(['My Workflow', 'Workflows']))
  },
}

export const AppTitleOnly: Story = {
  name: 'App title only (empty segments)',
  args: { segments: [] },
  play: async () => {
    await expect(document.title).toBe(toPageTitle([]))
  },
}

export const FiltersNullish: Story = {
  name: 'Null/undefined segments are filtered',
  args: { segments: [undefined, null, 'Workflows'] },
  play: async () => {
    await expect(document.title).toBe(toPageTitle([undefined, null, 'Workflows']))
  },
}

export const DynamicSegment: Story = {
  name: 'Dynamic first segment (e.g. item name)',
  args: { segments: ['ansible-lint-check', 'Workflows'] },
  play: async () => {
    await expect(document.title).toBe(toPageTitle(['ansible-lint-check', 'Workflows']))
  },
}
