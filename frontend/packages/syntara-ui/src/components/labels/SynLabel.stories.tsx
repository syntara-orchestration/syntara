import { Flex, FlexItem } from '@patternfly/react-core'
import {
  RhUiCheckCircleIcon,
  RhUiCloseCircleIcon,
  RhUiHourglassIcon,
  RhUiInformationIcon,
  RhUiSyncIcon,
  RhUiWarningIcon,
} from '@patternfly/react-icons'
import type { Meta, StoryObj } from '@storybook/react-vite'

import { SynLabel } from './SynLabel'

const meta: Meta<typeof SynLabel> = {
  component: SynLabel,
  tags: ['autodocs'],
  parameters: {
    docs: {
      description: {
        component:
          'Standard application label. Defaults to `variant="filled"` and `isCompact={true}`.\n\n' +
          'Use for all system-generated labels: statuses, categories, metadata badges, and counts. ' +
          'Pass `status` and `icon` for status indicators; pass `color` for categorical labels.\n\n' +
          'For user-authored tags (workflow tags, user-entered values), use `SynUserTag` instead.',
      },
    },
  },
}
export default meta

type Story = StoryObj<typeof meta>

/** Default usage with a status and icon. */
export const Default: Story = {
  args: {
    status: 'success',
    icon: <RhUiCheckCircleIcon />,
    children: 'Completed',
  },
}

/** All five PatternFly `status` values. */
export const AllStatuses: Story = {
  render: () => (
    <Flex gap={{ default: 'gapSm' }}>
      <FlexItem>
        <SynLabel status="success" icon={<RhUiCheckCircleIcon />}>
          Success
        </SynLabel>
      </FlexItem>
      <FlexItem>
        <SynLabel status="danger" icon={<RhUiCloseCircleIcon />}>
          Danger
        </SynLabel>
      </FlexItem>
      <FlexItem>
        <SynLabel status="warning" icon={<RhUiWarningIcon />}>
          Warning
        </SynLabel>
      </FlexItem>
      <FlexItem>
        <SynLabel status="info" icon={<RhUiInformationIcon />}>
          Info
        </SynLabel>
      </FlexItem>
      <FlexItem>
        <SynLabel status="custom" icon={<RhUiSyncIcon />}>
          Custom
        </SynLabel>
      </FlexItem>
    </Flex>
  ),
}

/** Categorical labels using `color` for semantic distinction. */
export const ColorVariants: Story = {
  render: () => (
    <Flex gap={{ default: 'gapSm' }}>
      <FlexItem>
        <SynLabel color="blue">System</SynLabel>
      </FlexItem>
      <FlexItem>
        <SynLabel color="green">Project</SynLabel>
      </FlexItem>
      <FlexItem>
        <SynLabel color="purple">Custom</SynLabel>
      </FlexItem>
      <FlexItem>
        <SynLabel color="grey">Built-in</SynLabel>
      </FlexItem>
      <FlexItem>
        <SynLabel color="teal">User</SynLabel>
      </FlexItem>
      <FlexItem>
        <SynLabel color="orange">Group</SynLabel>
      </FlexItem>
    </Flex>
  ),
}

/** Without an icon. */
export const WithoutIcon: Story = {
  render: () => (
    <Flex gap={{ default: 'gapSm' }}>
      <FlexItem>
        <SynLabel status="success">Completed</SynLabel>
      </FlexItem>
      <FlexItem>
        <SynLabel status="danger">Failed</SynLabel>
      </FlexItem>
      <FlexItem>
        <SynLabel status="custom">Pending</SynLabel>
      </FlexItem>
    </Flex>
  ),
}

/** Full-size labels with `isCompact={false}`. */
export const FullSize: Story = {
  render: () => (
    <Flex gap={{ default: 'gapSm' }}>
      <FlexItem>
        <SynLabel status="success" icon={<RhUiCheckCircleIcon />} isCompact={false}>
          Completed
        </SynLabel>
      </FlexItem>
      <FlexItem>
        <SynLabel status="custom" icon={<RhUiHourglassIcon />} isCompact={false}>
          Pending
        </SynLabel>
      </FlexItem>
    </Flex>
  ),
}
