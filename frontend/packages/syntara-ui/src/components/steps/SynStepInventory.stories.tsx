import { Content, ContentVariants, Flex, FlexItem, Stack, StackItem, Title, TitleSizes } from '@patternfly/react-core'
import { RhUiWarningFillIcon } from '@patternfly/react-icons'
import type { Meta, StoryObj } from '@storybook/tanstack-react'
import { ExecutorTypeEnum } from '@syntara/contracts'
import { userEvent, within } from 'storybook/test'

import { FlowNodeType } from '../../constants'
import { StandardStepHeader } from '../../routes/workflows/canvas/nodes/common/StandardStepHeader'
import { STEP_TYPE_COLORS } from '../../routes/workflows/canvas/stepTypeColors'

import { SynStep } from './SynStep'
import {
  createNodeProps,
  EXECUTION_STATES,
  FullStepStoryComposition,
  StepExample,
  StepStoryCanvas,
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
          <StepExample label="Full composition">
            <FullStepStoryComposition
              id="inventory-base"
              description="Synchronize inventory across the selected managed hosts."
            />
          </StepExample>
          <StepExample label="Selected dashed placeholder">
            <SynStep
              nodeProps={createNodeProps({ id: 'inventory-selected', selected: true, type: FlowNodeType.GENERIC })}
              hasDashedBorder
            >
              <StandardStepHeader title="Selected placeholder" />
            </SynStep>
          </StepExample>
          <StepExample label="Disabled validation error with mock data pinned">
            <SynStep
              nodeProps={createNodeProps({
                id: 'inventory-disabled-invalid',
                data: { settings: { disabled: true }, __validationError: true, metadata: { __mockDataPinned: true } },
              })}
              topBarColor={STEP_TYPE_COLORS.logic}
            >
              <StandardStepHeader title="Invalid pinned condition" />
            </SynStep>
          </StepExample>
          <StepExample label="Collapsed content" testId="collapsed-content-example">
            <SynStep
              nodeProps={createNodeProps({ id: 'inventory-collapsed' })}
              topBarColor={STEP_TYPE_COLORS.actionScript}
            >
              <StandardStepHeader expandable title="Collapsed task" />
              <SynStepBody>
                <Content component={ContentVariants.small}>Hidden until expanded.</Content>
              </SynStepBody>
            </SynStep>
          </StepExample>
          <StepExample label="Generic wide node">
            <SynStep
              nodeProps={createNodeProps({ id: 'inventory-generic', type: FlowNodeType.GENERIC })}
              hasDashedBorder
            >
              <StandardStepHeader title="Generic placeholder" />
            </SynStep>
          </StepExample>
          <StepExample label="Agentic wide task">
            <SynStep
              nodeProps={createNodeProps({ id: 'inventory-agentic', data: { type: ExecutorTypeEnum.AGENTIC } })}
              topBarColor={STEP_TYPE_COLORS.actionAgentic}
            >
              <StandardStepHeader title="Agentic task" />
            </SynStep>
          </StepExample>
          <StepExample label="Reversed source/target; visible start and hidden end">
            <SynStep
              nodeProps={createNodeProps({ id: 'inventory-handles' })}
              enableEnd
              enableStart
              reverseHandles
              topBarColor={STEP_TYPE_COLORS.logic}
            >
              <StandardStepHeader title="Branch handles" />
            </SynStep>
          </StepExample>
          <StepExample label="No source or target handle">
            <SynStep
              disableSource
              disableTarget
              nodeProps={createNodeProps({ id: 'inventory-no-handles' })}
              topBarColor={STEP_TYPE_COLORS.logic}
            >
              <StandardStepHeader title="No handles" />
            </SynStep>
          </StepExample>
          <StepExample label="Subtitle-only title">
            <SynStep nodeProps={createNodeProps({ id: 'inventory-subtitle' })} topBarColor={STEP_TYPE_COLORS.logic}>
              <StandardStepHeader subtitle="Fallback title from subtitle" />
            </SynStep>
          </StepExample>
          {EXECUTION_STATES.map((executionState) => (
            <StepExample key={executionState.status} label={`${executionState.status} execution state`}>
              <SynStep
                executionState={executionState}
                nodeProps={createNodeProps({
                  id: `inventory-${executionState.status}`,
                  name: `${executionState.status} task`,
                })}
                topBarColor={STEP_TYPE_COLORS.actionScript}
              >
                <StandardStepHeader title={`${executionState.status} task`} />
              </SynStep>
            </StepExample>
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
      <StepStoryCanvas minimumHeight={1280}>
        <Story />
      </StepStoryCanvas>
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
