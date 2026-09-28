import { Content, ContentVariants, Flex, FlexItem, Stack, StackItem, Title, TitleSizes } from '@patternfly/react-core'
import { RhUiWarningFillIcon } from '@patternfly/react-icons'
import type { Meta, StoryObj } from '@storybook/tanstack-react'
import { ExecutorTypeEnum } from '@syntara/contracts'
import { userEvent, within } from 'storybook/test'

import { FlowNodeType } from '../../constants'
import { StandardNodeHeader } from '../../routes/workflows/canvas/nodes/common/StandardNodeHeader'
import { NODE_TYPE_COLORS } from '../../routes/workflows/canvas/nodeTypeColors'

import { SynStepComponent } from './SynStepComponent'
import { SynStepBody } from './SynStepBody'
import {
  createNodeProps,
  EXECUTION_STATES,
  FullNodeStoryComposition,
  NodeExample,
  NodeStoryCanvas,
} from './SynStepComponent.stories.helpers'
import styles from './SynStepComponent.stories.module.css'

function SynStepInventory() {
  return (
    <Stack hasGutter>
      <StackItem>
        <Title headingLevel="h2" size={TitleSizes.lg}>
          Global step state inventory
        </Title>
      </StackItem>
      <StackItem>
        <div className={styles.gallery}>
          <NodeExample label="Full composition">
            <FullNodeStoryComposition
              id="inventory-base"
              description="Synchronize inventory across the selected managed hosts."
            />
          </NodeExample>
          <NodeExample label="Selected dashed placeholder">
            <SynStepComponent
              nodeProps={createNodeProps({ id: 'inventory-selected', selected: true, type: FlowNodeType.GENERIC })}
              hasDashedBorder
            >
              <StandardNodeHeader title="Selected placeholder" />
            </SynStepComponent>
          </NodeExample>
          <NodeExample label="Disabled validation error with mock data pinned">
            <SynStepComponent
              nodeProps={createNodeProps({
                id: 'inventory-disabled-invalid',
                data: { settings: { disabled: true }, __validationError: true, metadata: { __mockDataPinned: true } },
              })}
              topBarColor={NODE_TYPE_COLORS.logic}
            >
              <StandardNodeHeader title="Invalid pinned condition" />
            </SynStepComponent>
          </NodeExample>
          <NodeExample label="Collapsed content" testId="collapsed-content-example">
            <SynStepComponent
              nodeProps={createNodeProps({ id: 'inventory-collapsed' })}
              topBarColor={NODE_TYPE_COLORS.actionScript}
            >
              <StandardNodeHeader expandable title="Collapsed task" />
              <SynStepBody>
                <Content component={ContentVariants.small}>Hidden until expanded.</Content>
              </SynStepBody>
            </SynStepComponent>
          </NodeExample>
          <NodeExample label="Generic wide node">
            <SynStepComponent
              nodeProps={createNodeProps({ id: 'inventory-generic', type: FlowNodeType.GENERIC })}
              hasDashedBorder
            >
              <StandardNodeHeader title="Generic placeholder" />
            </SynStepComponent>
          </NodeExample>
          <NodeExample label="Agentic wide task">
            <SynStepComponent
              nodeProps={createNodeProps({ id: 'inventory-agentic', data: { type: ExecutorTypeEnum.AGENTIC } })}
              topBarColor={NODE_TYPE_COLORS.actionAgentic}
            >
              <StandardNodeHeader title="Agentic task" />
            </SynStepComponent>
          </NodeExample>
          <NodeExample label="Reversed source/target; visible start and hidden end">
            <SynStepComponent
              nodeProps={createNodeProps({ id: 'inventory-handles' })}
              enableEnd
              enableStart
              reverseHandles
              topBarColor={NODE_TYPE_COLORS.logic}
            >
              <StandardNodeHeader title="Branch handles" />
            </SynStepComponent>
          </NodeExample>
          <NodeExample label="No source or target handle">
            <SynStepComponent
              disableSource
              disableTarget
              nodeProps={createNodeProps({ id: 'inventory-no-handles' })}
              topBarColor={NODE_TYPE_COLORS.logic}
            >
              <StandardNodeHeader title="No handles" />
            </SynStepComponent>
          </NodeExample>
          <NodeExample label="Subtitle-only title">
            <SynStepComponent
              nodeProps={createNodeProps({ id: 'inventory-subtitle' })}
              topBarColor={NODE_TYPE_COLORS.logic}
            >
              <StandardNodeHeader subtitle="Fallback title from subtitle" />
            </SynStepComponent>
          </NodeExample>
          {EXECUTION_STATES.map((executionState) => (
            <NodeExample key={executionState.status} label={`${executionState.status} execution state`}>
              <SynStepComponent
                executionState={executionState}
                nodeProps={createNodeProps({
                  id: `inventory-${executionState.status}`,
                  name: `${executionState.status} task`,
                })}
                topBarColor={NODE_TYPE_COLORS.actionScript}
              >
                <StandardNodeHeader title={`${executionState.status} task`} />
              </SynStepComponent>
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
  title: 'components/nodes/SynStepComponent',
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

/** Fixed visual inventory for shared step states. Menus remain closed so no popover obscures adjacent nodes. */
export const Inventory: Story = {
  render: () => <SynStepInventory />,
  play: async ({ canvas }) => {
    const collapsedExample = within(canvas.getByTestId('collapsed-content-example'))
    await userEvent.click(collapsedExample.getByRole('button', { name: 'Collapse step details' }))
  },
}
