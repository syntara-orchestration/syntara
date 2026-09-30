import { Content, ContentVariants, Flex, FlexItem, Stack, StackItem, Title, TitleSizes } from '@patternfly/react-core'
import { RhUiWarningFillIcon } from '@patternfly/react-icons'
import type { Meta, StoryObj } from '@storybook/tanstack-react'
import { ExecutorTypeEnum } from '@syntara/contracts'
import { userEvent, within } from 'storybook/test'

import { FlowNodeType } from '../../constants'
import { StandardNodeHeader } from '../../routes/workflows/canvas/nodes/common/StandardNodeHeader'
import { NODE_TYPE_COLORS } from '../../routes/workflows/canvas/nodeTypeColors'

import { SynStep } from './SynStep'
import {
  createNodeProps,
  EXECUTION_STATES,
  FullNodeStoryComposition,
  NodeExample,
  NodeStoryCanvas,
} from './SynStep.stories.helpers'
import styles from './SynStep.stories.module.css'
import { SynStepBody } from './SynStepBody'

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
            <SynStep
              nodeProps={createNodeProps({ id: 'inventory-selected', selected: true, type: FlowNodeType.GENERIC })}
              hasDashedBorder
            >
              <StandardNodeHeader title="Selected placeholder" />
            </SynStep>
          </NodeExample>
          <NodeExample label="Disabled validation error with mock data pinned">
            <SynStep
              nodeProps={createNodeProps({
                id: 'inventory-disabled-invalid',
                data: { settings: { disabled: true }, __validationError: true, metadata: { __mockDataPinned: true } },
              })}
              topBarColor={NODE_TYPE_COLORS.logic}
            >
              <StandardNodeHeader title="Invalid pinned condition" />
            </SynStep>
          </NodeExample>
          <NodeExample label="Collapsed content" testId="collapsed-content-example">
            <SynStep
              nodeProps={createNodeProps({ id: 'inventory-collapsed' })}
              topBarColor={NODE_TYPE_COLORS.actionScript}
            >
              <StandardNodeHeader expandable title="Collapsed task" />
              <SynStepBody>
                <Content component={ContentVariants.small}>Hidden until expanded.</Content>
              </SynStepBody>
            </SynStep>
          </NodeExample>
          <NodeExample label="Generic wide node">
            <SynStep
              nodeProps={createNodeProps({ id: 'inventory-generic', type: FlowNodeType.GENERIC })}
              hasDashedBorder
            >
              <StandardNodeHeader title="Generic placeholder" />
            </SynStep>
          </NodeExample>
          <NodeExample label="Agentic wide task">
            <SynStep
              nodeProps={createNodeProps({ id: 'inventory-agentic', data: { type: ExecutorTypeEnum.AGENTIC } })}
              topBarColor={NODE_TYPE_COLORS.actionAgentic}
            >
              <StandardNodeHeader title="Agentic task" />
            </SynStep>
          </NodeExample>
          <NodeExample label="Reversed source/target; visible start and hidden end">
            <SynStep
              nodeProps={createNodeProps({ id: 'inventory-handles' })}
              enableEnd
              enableStart
              reverseHandles
              topBarColor={NODE_TYPE_COLORS.logic}
            >
              <StandardNodeHeader title="Branch handles" />
            </SynStep>
          </NodeExample>
          <NodeExample label="No source or target handle">
            <SynStep
              disableSource
              disableTarget
              nodeProps={createNodeProps({ id: 'inventory-no-handles' })}
              topBarColor={NODE_TYPE_COLORS.logic}
            >
              <StandardNodeHeader title="No handles" />
            </SynStep>
          </NodeExample>
          <NodeExample label="Subtitle-only title">
            <SynStep nodeProps={createNodeProps({ id: 'inventory-subtitle' })} topBarColor={NODE_TYPE_COLORS.logic}>
              <StandardNodeHeader subtitle="Fallback title from subtitle" />
            </SynStep>
          </NodeExample>
          {EXECUTION_STATES.map((executionState) => (
            <NodeExample key={executionState.status} label={`${executionState.status} execution state`}>
              <SynStep
                executionState={executionState}
                nodeProps={createNodeProps({
                  id: `inventory-${executionState.status}`,
                  name: `${executionState.status} task`,
                })}
                topBarColor={NODE_TYPE_COLORS.actionScript}
              >
                <StandardNodeHeader title={`${executionState.status} task`} />
              </SynStep>
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
  title: 'components/steps/SynStep',
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
