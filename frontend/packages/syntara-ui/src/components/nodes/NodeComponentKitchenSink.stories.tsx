import { Content, ContentVariants, Flex, FlexItem, Stack, StackItem, Title, TitleSizes } from '@patternfly/react-core'
import { RhUiDuplicateIcon, RhUiPlayIcon, RhUiTrashIcon, RhUiWarningFillIcon } from '@patternfly/react-icons'
import type { Meta, StoryObj } from '@storybook/tanstack-react'
import { ExecutorTypeEnum } from '@syntara/contracts'
import { userEvent } from 'storybook/test'

import { FlowNodeType } from '../../constants'
import { ACTIVITY_STATUS } from '../../routes/builder/utils/executionState/executionHelpers'
import { StandardNodeHeader } from '../../routes/workflows/canvas/nodes/common/StandardNodeHeader'
import { NODE_TYPE_COLORS } from '../../routes/workflows/canvas/nodeTypeColors'

import { NodeBody } from './NodeBody'
import { NodeComponent } from './NodeComponent'
import { createNodeProps, NodeExample, NodeStoryCanvas } from './NodeComponent.stories.helpers'
import styles from './NodeComponent.stories.module.css'

const MENU_ACTIONS = [
  { id: 'run', label: 'Run step', onClick: () => undefined, icon: <RhUiPlayIcon /> },
  { id: 'duplicate', label: 'Duplicate', onClick: () => undefined, icon: <RhUiDuplicateIcon /> },
  { id: 'separator', label: '', onClick: () => undefined, separator: true },
  { id: 'delete', label: 'Delete', onClick: () => undefined, icon: <RhUiTrashIcon />, variant: 'danger' as const },
]

function KitchenSinkInventory() {
  return (
    <Stack hasGutter>
      <StackItem>
        <Title headingLevel="h2" size={TitleSizes.lg}>
          Global node state inventory
        </Title>
      </StackItem>
      <StackItem>
        <div className={styles.gallery}>
          <NodeExample label="Full composition">
            <NodeComponent
              nodeProps={createNodeProps({ id: 'kitchen-base' })}
              topBarColor={NODE_TYPE_COLORS.actionScript}
            >
              <StandardNodeHeader
                expandable
                menuActions={MENU_ACTIONS}
                subtitle="Script task"
                title="Run inventory synchronization"
              />
            </NodeComponent>
          </NodeExample>
          <NodeExample label="Selected dashed placeholder">
            <NodeComponent
              nodeProps={createNodeProps({ id: 'kitchen-selected', selected: true, type: FlowNodeType.GENERIC })}
              hasDashedBorder
            >
              <StandardNodeHeader title="Selected placeholder" />
            </NodeComponent>
          </NodeExample>
          <NodeExample label="Disabled validation error with mock data pinned">
            <NodeComponent
              nodeProps={createNodeProps({
                id: 'kitchen-disabled-invalid',
                data: { settings: { disabled: true }, __validationError: true, metadata: { __mockDataPinned: true } },
              })}
              topBarColor={NODE_TYPE_COLORS.logic}
            >
              <StandardNodeHeader title="Invalid pinned condition" />
            </NodeComponent>
          </NodeExample>
          <NodeExample label="Collapsed content">
            <NodeComponent
              nodeProps={createNodeProps({ id: 'kitchen-collapsed' })}
              topBarColor={NODE_TYPE_COLORS.actionScript}
            >
              <StandardNodeHeader expandable title="Collapsed task" />
              <NodeBody>
                <Content component={ContentVariants.small}>Hidden until expanded.</Content>
              </NodeBody>
            </NodeComponent>
          </NodeExample>
          <NodeExample label="Generic wide node">
            <NodeComponent
              nodeProps={createNodeProps({ id: 'kitchen-generic', type: FlowNodeType.GENERIC })}
              hasDashedBorder
            >
              <StandardNodeHeader title="Generic placeholder" />
            </NodeComponent>
          </NodeExample>
          <NodeExample label="Agentic wide task">
            <NodeComponent
              nodeProps={createNodeProps({ id: 'kitchen-agentic', data: { type: ExecutorTypeEnum.AGENTIC } })}
              topBarColor={NODE_TYPE_COLORS.actionAgentic}
            >
              <StandardNodeHeader title="Agentic task" />
            </NodeComponent>
          </NodeExample>
          <NodeExample label="Reversed start and end handles">
            <NodeComponent
              nodeProps={createNodeProps({ id: 'kitchen-handles' })}
              enableEnd
              enableStart
              reverseHandles
              topBarColor={NODE_TYPE_COLORS.logic}
            >
              <StandardNodeHeader title="Branch handles" />
            </NodeComponent>
          </NodeExample>
          <NodeExample label="No source or target handle">
            <NodeComponent
              disableSource
              disableTarget
              nodeProps={createNodeProps({ id: 'kitchen-no-handles' })}
              topBarColor={NODE_TYPE_COLORS.logic}
            >
              <StandardNodeHeader title="No handles" />
            </NodeComponent>
          </NodeExample>
          <NodeExample label="Subtitle-only title">
            <NodeComponent nodeProps={createNodeProps({ id: 'kitchen-subtitle' })} topBarColor={NODE_TYPE_COLORS.logic}>
              <StandardNodeHeader subtitle="Fallback title from subtitle" />
            </NodeComponent>
          </NodeExample>
          {Object.values(ACTIVITY_STATUS).map((status) => (
            <NodeExample key={status} label={`${status} execution state`}>
              <NodeComponent
                executionState={{ status, retry_count: status === ACTIVITY_STATUS.RETRYING ? 2 : undefined }}
                nodeProps={createNodeProps({ id: `kitchen-${status}`, name: `${status} task` })}
                topBarColor={NODE_TYPE_COLORS.actionScript}
              >
                <StandardNodeHeader title={`${status} task`} />
              </NodeComponent>
            </NodeExample>
          ))}
        </div>
      </StackItem>
      <StackItem>
        <Flex gap={{ default: 'gapSm' }}>
          <FlexItem>
            <RhUiWarningFillIcon />
          </FlexItem>
          <FlexItem>
            <Content component={ContentVariants.small}>Menus remain closed so the gallery stays readable.</Content>
          </FlexItem>
        </Flex>
      </StackItem>
    </Stack>
  )
}

const meta: Meta = {
  title: 'components/nodes/NodeComponent',
  decorators: [
    (Story) => (
      <NodeStoryCanvas minimumHeight={1280}>
        <Story />
      </NodeStoryCanvas>
    ),
  ],
  parameters: { controls: { disable: true } },
}

export default meta
type Story = StoryObj<typeof meta>

/** Fixed visual inventory for global-node states. Menus remain closed so no popover obscures adjacent nodes. */
export const Inventory: Story = {
  render: () => <KitchenSinkInventory />,
  play: async ({ canvas }) => {
    const [collapsedToggle] = canvas.getAllByRole('button', { name: 'Collapse step details' })
    if (collapsedToggle) await userEvent.click(collapsedToggle)
  },
}
