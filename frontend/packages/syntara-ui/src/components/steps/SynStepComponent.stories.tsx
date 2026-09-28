import { Content, ContentVariants } from '@patternfly/react-core'
import type { Meta, StoryObj } from '@storybook/tanstack-react'
import { ExecutorTypeEnum } from '@syntara/contracts'
import { ReactFlow, type Node, type NodeProps } from '@xyflow/react'
import { userEvent } from 'storybook/test'

import { FlowNodeType } from '../../constants'
import { StandardNodeHeader } from '../../routes/workflows/canvas/nodes/common/StandardNodeHeader'
import { NODE_TYPE_COLORS } from '../../routes/workflows/canvas/nodeTypeColors'

import { SynStepComponent } from './SynStepComponent'
import { SynStepBody } from './SynStepBody'
import {
  createNodeProps,
  EXECUTION_STATES,
  FullNodeStoryComposition,
  MENU_ACTIONS,
  NodeExample,
  NodeStoryCanvas,
  type StoryNodeData,
} from './SynStepComponent.stories.helpers'
import styles from './SynStepComponent.stories.module.css'
import { SynStepExpandToggle } from './SynStepExpandToggle'
import { SynStepHeader } from './SynStepHeader'
import { SynStepTitle } from './SynStepTitle'

type NodeStoryParameters = {
  storyCanvas?: { minimumHeight?: number }
  withoutStoryCanvas?: boolean
}

type SemanticZoomFlowNode = Node<StoryNodeData, 'semanticZoom'>

function SemanticZoomNode(props: NodeProps<SemanticZoomFlowNode>) {
  return (
    <SynStepComponent
      nodeProps={props}
      topBarColor={NODE_TYPE_COLORS.logic}
      semanticZoomSummary={{ title: props.data.name, typeLabel: 'Condition' }}
      semanticZoomBranchSources={[
        { id: 'true', ariaLabel: 'True branch' },
        { id: 'false', ariaLabel: 'False branch' },
      ]}
      hasDashedBorder={props.data.settings?.disabled === true}
    >
      <SynStepHeader>
        <SynStepExpandToggle nodeLabel={props.data.name} />
        <SynStepTitle title={props.data.name} subTitle="Condition" />
      </SynStepHeader>
      <SynStepBody>Detailed content is visible above the semantic-zoom threshold.</SynStepBody>
    </SynStepComponent>
  )
}

const semanticNodeTypes = { semanticZoom: SemanticZoomNode }

const meta: Meta<typeof SynStepComponent> = {
  component: SynStepComponent,
  tags: ['autodocs'],
  decorators: [
    (Story, context) =>
      (context.parameters as NodeStoryParameters).withoutStoryCanvas ? (
        <Story />
      ) : (
        <NodeStoryCanvas minimumHeight={(context.parameters as NodeStoryParameters).storyCanvas?.minimumHeight}>
          <Story />
        </NodeStoryCanvas>
      ),
  ],
  parameters: {
    docs: {
      description: {
        component:
          'Shared composition primitives for workflow steps. Compose `SynStepComponent` with `SynStepHeader`, ' +
          '`SynStepExpandToggle`, `SynStepTitle`, `SynStepMenu`, and `SynStepBody` to build a complete node. ' +
          'State owned by the workflow node belongs in `nodeProps.data` (for example `settings.disabled`, ' +
          '`__validationError`, and `metadata.__mockDataPinned`); visual layout options belong on `SynStepComponent`. ' +
          'The Inventory story is the fixed visual inventory for supported shared step states.',
      },
    },
  },
}

export default meta

type Story = StoryObj<typeof meta>

/** A realistic node composition with its header, body, handles, and action menu. */
export const Default: Story = {
  render: () => (
    <FullNodeStoryComposition id="default" description="Collect inventory from the selected managed hosts." />
  ),
}

/** Selection uses an outline without changing the node's box geometry. */
export const Selected: Story = {
  render: () => (
    <SynStepComponent
      nodeProps={createNodeProps({ id: 'selected', selected: true })}
      topBarColor={NODE_TYPE_COLORS.actionScript}
    >
      <StandardNodeHeader
        expandable
        menuActions={MENU_ACTIONS}
        subtitle="Script task"
        title="Run inventory synchronization"
      />
      <SynStepBody>
        <Content component={ContentVariants.small}>
          The selected node keeps its normal type indicator and content.
        </Content>
      </SynStepBody>
    </SynStepComponent>
  ),
}

/** Disabled and validation-error states combine the production data flags with representative node content. */
export const DisabledAndValidationError: Story = {
  render: () => (
    <div className={styles.comparisonGrid}>
      <SynStepComponent
        nodeProps={createNodeProps({ id: 'disabled', data: { settings: { disabled: true } } })}
        topBarColor={NODE_TYPE_COLORS.actionScript}
      >
        <SynStepHeader>
          <SynStepExpandToggle nodeLabel="Disabled deployment" />
          <SynStepTitle title="Disabled deployment" subTitle="Script task" />
        </SynStepHeader>
        <SynStepBody>
          <Content component={ContentVariants.small}>This step will be skipped when the workflow runs.</Content>
        </SynStepBody>
      </SynStepComponent>
      <SynStepComponent
        nodeProps={createNodeProps({ id: 'validation', data: { __validationError: true } })}
        topBarColor={NODE_TYPE_COLORS.logic}
      >
        <SynStepHeader>
          <SynStepExpandToggle nodeLabel="Check deployment policy" />
          <SynStepTitle title="Check deployment policy" subTitle="Condition" />
        </SynStepHeader>
        <SynStepBody>
          <Content component={ContentVariants.small}>The condition needs a valid expression before it can run.</Content>
        </SynStepBody>
      </SynStepComponent>
    </div>
  ),
}

/** Every contract-supported execution status, including a retry count for the retrying state. */
export const ExecutionStates: Story = {
  parameters: { storyCanvas: { minimumHeight: 640 } },
  render: () => (
    <div className={styles.gallery}>
      {EXECUTION_STATES.map((executionState) => (
        <NodeExample key={executionState.status} label={executionState.status}>
          <SynStepComponent
            nodeProps={createNodeProps({
              id: `execution-${executionState.status}`,
              name: `${executionState.status} task`,
            })}
            executionState={executionState}
            topBarColor={NODE_TYPE_COLORS.actionScript}
          >
            <SynStepHeader>
              <SynStepTitle title={`${executionState.status} task`} subTitle="Script task" />
            </SynStepHeader>
            <SynStepBody>
              <Content component={ContentVariants.small}>Execution badge shown below the node.</Content>
            </SynStepBody>
          </SynStepComponent>
        </NodeExample>
      ))}
    </div>
  ),
}

/** Expanded and collapsed states use the same production expand-toggle interaction. */
export const CollapsedAndExpanded: Story = {
  render: () => (
    <div className={styles.comparisonGrid}>
      <SynStepComponent nodeProps={createNodeProps({ id: 'expanded' })} topBarColor={NODE_TYPE_COLORS.actionScript}>
        <SynStepHeader>
          <SynStepExpandToggle nodeLabel="Expanded node" />
          <SynStepTitle title="Expanded node" subTitle="Script task" />
        </SynStepHeader>
        <SynStepBody>
          <Content component={ContentVariants.small}>
            The body is visible initially and may be collapsed with the caret.
          </Content>
        </SynStepBody>
      </SynStepComponent>
      <SynStepComponent nodeProps={createNodeProps({ id: 'collapsed' })} topBarColor={NODE_TYPE_COLORS.actionScript}>
        <SynStepHeader>
          <SynStepExpandToggle nodeLabel="Collapsed node" />
          <SynStepTitle title="Collapsed node" subTitle="Script task" />
        </SynStepHeader>
        <SynStepBody>
          <Content component={ContentVariants.small}>This body appears after expanding the node.</Content>
        </SynStepBody>
      </SynStepComponent>
    </div>
  ),
  play: async ({ canvas }) => {
    await userEvent.click(canvas.getByRole('button', { name: 'Collapse details for Collapsed node' }))
  },
}

/** The menu begins closed; open it to inspect normal, icon, separated, and danger actions. */
export const Menu: Story = {
  render: () => (
    <SynStepComponent nodeProps={createNodeProps({ id: 'menu' })} topBarColor={NODE_TYPE_COLORS.actionScript}>
      <StandardNodeHeader expandable menuActions={MENU_ACTIONS} subtitle="Script task" title="Node action menu" />
      <SynStepBody>
        <Content component={ContentVariants.small}>Use the kebab button to open the node actions.</Content>
      </SynStepBody>
    </SynStepComponent>
  ),
}

/** Semantic zoom renders the compact node body through a real React Flow viewport at 0.5 zoom. */
export const SemanticZoom: Story = {
  parameters: { withoutStoryCanvas: true },
  render: () => {
    const nodes: Node<StoryNodeData>[] = [
      {
        id: 'semantic-normal',
        type: 'semanticZoom',
        position: { x: 100, y: 70 },
        data: { id: 'semantic-normal', name: 'Evaluate deployment policy', type: FlowNodeType.TASK },
      },
      {
        id: 'semantic-selected',
        type: 'semanticZoom',
        selected: true,
        position: { x: 460, y: 70 },
        data: { id: 'semantic-selected', name: 'Selected condition', type: FlowNodeType.TASK },
      },
      {
        id: 'semantic-dashed',
        type: 'semanticZoom',
        position: { x: 820, y: 70 },
        data: {
          id: 'semantic-dashed',
          name: 'Disabled condition',
          type: FlowNodeType.TASK,
          settings: { disabled: true },
        },
      },
    ]

    return (
      <div className={styles.semanticZoomCanvas}>
        <ReactFlow
          fitView
          fitViewOptions={{ padding: 0.2 }}
          minZoom={0.5}
          maxZoom={0.5}
          nodes={nodes}
          nodeTypes={semanticNodeTypes}
          nodesConnectable={false}
          nodesDraggable={false}
          panOnDrag={false}
          panOnScroll={false}
          preventScrolling={false}
          proOptions={{ hideAttribution: true }}
          zoomOnDoubleClick={false}
          zoomOnPinch={false}
          zoomOnScroll={false}
        />
      </div>
    )
  },
}

/** Default, generic, and agentic task widths are fixed by the global node contract. */
export const WidthsAndTypes: Story = {
  render: () => (
    <div className={styles.comparisonGrid}>
      <NodeExample label="Default task (240 px)">
        <SynStepComponent nodeProps={createNodeProps({ id: 'default-width' })} topBarColor={NODE_TYPE_COLORS.actionScript}>
          <SynStepHeader>
            <SynStepTitle title="Default task" subTitle="Script" />
          </SynStepHeader>
        </SynStepComponent>
      </NodeExample>
      <NodeExample label="Generic node (360 px)">
        <SynStepComponent
          nodeProps={createNodeProps({ id: 'generic-width', type: FlowNodeType.GENERIC })}
          hasDashedBorder
          topBarColor={NODE_TYPE_COLORS.generic}
        >
          <SynStepHeader>
            <SynStepTitle title="Generic placeholder" subTitle="Add a step" />
          </SynStepHeader>
        </SynStepComponent>
      </NodeExample>
      <NodeExample label="Agentic task (360 px)">
        <SynStepComponent
          nodeProps={createNodeProps({
            id: 'agentic-width',
            data: { type: ExecutorTypeEnum.AGENTIC, name: 'Agentic investigation' },
          })}
          topBarColor={NODE_TYPE_COLORS.actionAgentic}
        >
          <SynStepHeader>
            <SynStepTitle title="Agentic investigation" subTitle="Agentic task" />
          </SynStepHeader>
        </SynStepComponent>
      </NodeExample>
    </div>
  ),
}

/** Handle configurations are shown together because they alter the canvas connection affordances. */
export const Handles: Story = {
  render: () => (
    <div className={styles.gallery}>
      <NodeExample label="Default source and target">
        <SynStepComponent nodeProps={createNodeProps({ id: 'handles-default' })} topBarColor={NODE_TYPE_COLORS.logic}>
          <SynStepHeader>
            <SynStepTitle title="Default handles" />
          </SynStepHeader>
        </SynStepComponent>
      </NodeExample>
      <NodeExample label="Reversed handles">
        <SynStepComponent
          nodeProps={createNodeProps({ id: 'handles-reversed' })}
          reverseHandles
          topBarColor={NODE_TYPE_COLORS.logic}
        >
          <SynStepHeader>
            <SynStepTitle title="Reversed handles" />
          </SynStepHeader>
        </SynStepComponent>
      </NodeExample>
      <NodeExample label="Visible start handle; hidden loop-end target">
        <SynStepComponent
          nodeProps={createNodeProps({ id: 'handles-start-end' })}
          enableStart
          enableEnd
          topBarColor={NODE_TYPE_COLORS.logic}
        >
          <SynStepHeader>
            <SynStepTitle title="Loop start and end target" />
          </SynStepHeader>
        </SynStepComponent>
      </NodeExample>
      <NodeExample label="Source and target disabled">
        <SynStepComponent
          nodeProps={createNodeProps({ id: 'handles-disabled' })}
          disableSource
          disableTarget
          topBarColor={NODE_TYPE_COLORS.logic}
        >
          <SynStepHeader>
            <SynStepTitle title="No connection handles" />
          </SynStepHeader>
        </SynStepComponent>
      </NodeExample>
    </div>
  ),
}
