import { Content, ContentVariants, Flex, FlexItem, Stack, StackItem, Title, TitleSizes } from '@patternfly/react-core'
import { RhUiWarningFillIcon } from '@patternfly/react-icons'
import type { Meta, StoryObj } from '@storybook/tanstack-react'
import { ExecutorTypeEnum } from '@syntara/contracts'
import { userEvent, within } from 'storybook/test'

import { FlowNodeType } from '../../constants'
import { StandardNodeHeader } from '../../routes/workflows/canvas/nodes/common/StandardNodeHeader'
import { NODE_TYPE_COLORS } from '../../routes/workflows/canvas/nodeTypeColors'

import { NodeBody } from './NodeBody'
import { NodeComponent } from './NodeComponent'
import {
  createNodeProps,
  EXECUTION_STATES,
  MENU_ACTIONS,
  NodeExample,
  NodeStoryCanvas,
} from './NodeComponent.stories.helpers'
import styles from './NodeComponent.stories.module.css'

function NodeComponentInventory() {
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
              nodeProps={createNodeProps({ id: 'inventory-base' })}
              topBarColor={NODE_TYPE_COLORS.actionScript}
            >
              <StandardNodeHeader
                expandable
                menuActions={MENU_ACTIONS}
                subtitle="Script task"
                title="Run inventory synchronization"
              />
              <NodeBody>
                <Content component={ContentVariants.small}>
                  Synchronize inventory across the selected managed hosts.
                </Content>
              </NodeBody>
            </NodeComponent>
          </NodeExample>
          <NodeExample label="Selected dashed placeholder">
            <NodeComponent
              nodeProps={createNodeProps({ id: 'inventory-selected', selected: true, type: FlowNodeType.GENERIC })}
              hasDashedBorder
            >
              <StandardNodeHeader title="Selected placeholder" />
            </NodeComponent>
          </NodeExample>
          <NodeExample label="Disabled validation error with mock data pinned">
            <NodeComponent
              nodeProps={createNodeProps({
                id: 'inventory-disabled-invalid',
                data: { settings: { disabled: true }, __validationError: true, metadata: { __mockDataPinned: true } },
              })}
              topBarColor={NODE_TYPE_COLORS.logic}
            >
              <StandardNodeHeader title="Invalid pinned condition" />
            </NodeComponent>
          </NodeExample>
          <NodeExample label="Collapsed content" testId="collapsed-content-example">
            <NodeComponent
              nodeProps={createNodeProps({ id: 'inventory-collapsed' })}
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
              nodeProps={createNodeProps({ id: 'inventory-generic', type: FlowNodeType.GENERIC })}
              hasDashedBorder
            >
              <StandardNodeHeader title="Generic placeholder" />
            </NodeComponent>
          </NodeExample>
          <NodeExample label="Agentic wide task">
            <NodeComponent
              nodeProps={createNodeProps({ id: 'inventory-agentic', data: { type: ExecutorTypeEnum.AGENTIC } })}
              topBarColor={NODE_TYPE_COLORS.actionAgentic}
            >
              <StandardNodeHeader title="Agentic task" />
            </NodeComponent>
          </NodeExample>
          <NodeExample label="Reversed source/target; visible start and hidden end">
            <NodeComponent
              nodeProps={createNodeProps({ id: 'inventory-handles' })}
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
              nodeProps={createNodeProps({ id: 'inventory-no-handles' })}
              topBarColor={NODE_TYPE_COLORS.logic}
            >
              <StandardNodeHeader title="No handles" />
            </NodeComponent>
          </NodeExample>
          <NodeExample label="Subtitle-only title">
            <NodeComponent
              nodeProps={createNodeProps({ id: 'inventory-subtitle' })}
              topBarColor={NODE_TYPE_COLORS.logic}
            >
              <StandardNodeHeader subtitle="Fallback title from subtitle" />
            </NodeComponent>
          </NodeExample>
          {EXECUTION_STATES.map(({ status, retry_count }) => (
            <NodeExample key={status} label={`${status} execution state`}>
              <NodeComponent
                executionState={{ status, retry_count }}
                nodeProps={createNodeProps({ id: `inventory-${status}`, name: `${status} task` })}
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
  render: () => <NodeComponentInventory />,
  play: async ({ canvas }) => {
    const collapsedExample = within(canvas.getByTestId('collapsed-content-example'))
    await userEvent.click(collapsedExample.getByRole('button', { name: 'Collapse step details' }))
  },
}
