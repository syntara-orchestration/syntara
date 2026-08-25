import { Flex, FlexItem, LabelGroup } from '@patternfly/react-core'
import type { Meta, StoryObj } from '@storybook/react-vite'
import { fn } from 'storybook/test'

import { SynUserTag } from './SynUserTag'

const meta: Meta<typeof SynUserTag> = {
  component: SynUserTag,
  tags: ['autodocs'],
  parameters: {
    docs: {
      description: {
        component:
          'Outline label for user-authored content — workflow tags, user-entered values.\n\n' +
          'Renders with `variant="outline"` hardcoded. For system-generated labels ' +
          '(statuses, categories, metadata), use `SynLabel` instead.',
      },
    },
  },
}
export default meta

type Story = StoryObj<typeof meta>

/** Single user tag. */
export const Default: Story = {
  args: {
    children: 'my-workflow-tag',
  },
}

/** Multiple tags in a LabelGroup. */
export const TagGroup: Story = {
  render: () => (
    <LabelGroup>
      <SynUserTag>production</SynUserTag>
      <SynUserTag>critical</SynUserTag>
      <SynUserTag>team-platform</SynUserTag>
    </LabelGroup>
  ),
}

/** Tags with a remove callback. */
export const Removable: Story = {
  render: () => (
    <Flex gap={{ default: 'gapSm' }}>
      <FlexItem>
        <SynUserTag onClose={fn()}>production</SynUserTag>
      </FlexItem>
      <FlexItem>
        <SynUserTag onClose={fn()}>critical</SynUserTag>
      </FlexItem>
    </Flex>
  ),
}
