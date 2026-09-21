import { Content, ContentVariants, StackItem } from '@patternfly/react-core'
import { RhUiDuplicateIcon, RhUiPlayIcon, RhUiTrashIcon } from '@patternfly/react-icons'
import type { Meta, StoryObj } from '@storybook/tanstack-react'
import { ExecutorTypeEnum } from '@syntara/contracts'
import { Background, BackgroundVariant, Position, ReactFlow, type Node, type NodeProps } from '@xyflow/react'
import { userEvent } from 'storybook/test'

import { FlowNodeType } from '../../constants'
import { ACTIVITY_STATUS } from '../../routes/builder/utils/executionState/executionHelpers'
import { StandardNodeHeader } from '../../routes/workflows/canvas/nodes/common/StandardNodeHeader'
import { NODE_TYPE_COLORS } from '../../routes/workflows/canvas/nodeTypeColors'

import { NodeBody } from './NodeBody'
import { NodeComponent } from './NodeComponent'
import styles from './NodeComponent.stories.module.css'
import { KitchenSinkGallery } from './NodeComponentStoryHelpers'
import { NodeExpandToggle } from './NodeExpandToggle'
import { NodeHeader } from './NodeHeader'
import { NodeSidePanel } from './NodeSidePanel'
import { NodeTitle } from './NodeTitle'

type StoryNodeData = Record<string, unknown> & {
  id: string
  name: string
  type: string
  __validationError?: boolean
  metadata?: { __mockDataPinned?: boolean }
  settings?: { disabled?: boolean }
}

type NodePropsOptions = {
  id: string
  name?: string
  selected?: boolean
  type?: string
  data?: Partial<StoryNodeData>
}

const menuActions = [
  { id: 'run', label: 'Run step', onClick: () => undefined, icon: <RhUiPlayIcon /> },
  { id: 'duplicate', label: 'Duplicate', onClick: () => undefined, icon: <RhUiDuplicateIcon /> },
  { id: 'separator', label: '', onClick: () => undefined, separator: true },
  { id: 'delete', label: 'Delete', onClick: () => undefined, icon: <RhUiTrashIcon />, variant: 'danger' as const },
]

const executionStatuses = Object.values(ACTIVITY_STATUS)

function createNodeProps(options: NodePropsOptions): NodeProps {
  const nodeType = options.type ?? FlowNodeType.TASK
  const data: StoryNodeData = {
    id: options.id,
    name: options.name ?? 'Run inventory synchronization',
    type: nodeType,
    ...options.data,
  }

  return {
    id: options.id,
    data,
    selected: options.selected ?? false,
    type: nodeType,
    dragging: false,
    zIndex: 0,
    positionAbsoluteX: 0,
    positionAbsoluteY: 0,
    isConnectable: true,
    sourcePosition: Position.Right,
    targetPosition: Position.Left,
  } as unknown as NodeProps
}

type StoryCanvasNode = Node<{ content: React.ReactNode }, 'storybook'>

function StoryCanvasNodeComponent(props: NodeProps<StoryCanvasNode>) {
  return <>{props.data.content}</>
}

const storyCanvasNodeTypes = { storybook: StoryCanvasNodeComponent }

type StoryCanvasOptions = {
  height?: string
}

type NodeStoryParameters = {
  storyCanvas?: StoryCanvasOptions
  withoutStoryCanvas?: boolean
}

function NodeStoryCanvas({ children, height = '32rem' }: Readonly<{ children: React.ReactNode } & StoryCanvasOptions>) {
  return (
    <div className={styles.storyCanvas} style={{ height }}>
      <ReactFlow
        defaultViewport={{ x: 0, y: 0, zoom: 1 }}
        fitView={false}
        nodes={[
          {
            id: 'storybook-node',
            type: 'storybook',
            position: { x: 64, y: 64 },
            data: { content: children },
            style: { width: 1200 },
          },
        ]}
        nodeTypes={storyCanvasNodeTypes}
        nodesConnectable={false}
        nodesDraggable={false}
        panOnDrag={false}
        panOnScroll={false}
        preventScrolling={false}
        proOptions={{ hideAttribution: true }}
        zoomOnDoubleClick={false}
        zoomOnPinch={false}
        zoomOnScroll={false}
      >
        <Background variant={BackgroundVariant.Dots} gap={20} size={1} />
      </ReactFlow>
    </div>
  )
}

function NodeExample({ label, children }: Readonly<{ label: string; children: React.ReactNode }>) {
  return (
    <div className={styles.nodeExample}>
      <Content component={ContentVariants.small} className={styles.nodeLabel}>
        {label}
      </Content>
      {children}
    </div>
  )
}

type SemanticZoomFlowNode = Node<StoryNodeData, 'semanticZoom'>

function SemanticZoomNode(props: NodeProps<SemanticZoomFlowNode>) {
  return (
    <NodeComponent
      nodeProps={props}
      topBarColor={NODE_TYPE_COLORS.logic}
      semanticZoomSummary={{ title: props.data.name, typeLabel: 'Condition' }}
      semanticZoomBranchSources={[
        { id: 'true', ariaLabel: 'True branch' },
        { id: 'false', ariaLabel: 'False branch' },
      ]}
      hasDashedBorder={props.data.settings?.disabled === true}
    >
      <NodeHeader>
        <NodeExpandToggle />
        <NodeTitle title={props.data.name} subTitle="Condition" />
      </NodeHeader>
      <NodeBody>Detailed content is visible above the semantic-zoom threshold.</NodeBody>
    </NodeComponent>
  )
}

const semanticNodeTypes = { semanticZoom: SemanticZoomNode }

const meta: Meta<typeof NodeComponent> = {
  component: NodeComponent,
  tags: ['autodocs'],
  decorators: [
    (Story, context) =>
      (context.parameters as NodeStoryParameters).withoutStoryCanvas ? (
        <Story />
      ) : (
        <NodeStoryCanvas height={(context.parameters as NodeStoryParameters).storyCanvas?.height}>
          <Story />
        </NodeStoryCanvas>
      ),
  ],
  parameters: {
    docs: {
      description: {
        component:
          'Global composition primitives for workflow canvas nodes. Compose `NodeComponent` with `NodeHeader`, ' +
          '`NodeExpandToggle`, `NodeTitle`, `NodeMenu`, `NodeBody`, and `NodeSidePanel` to build a complete node. ' +
          'State owned by the workflow node belongs in `nodeProps.data` (for example `settings.disabled`, ' +
          '`__validationError`, and `metadata.__mockDataPinned`); visual layout options belong on `NodeComponent`. ' +
          'The Kitchen Sink is the fixed visual inventory for supported global-node states.',
      },
    },
  },
}

export default meta

type Story = StoryObj<typeof meta>

/** A realistic node composition with its header, body, side panel, handles, and action menu. */
export const Default: Story = {
  render: () => (
    <NodeComponent nodeProps={createNodeProps({ id: 'default' })} topBarColor={NODE_TYPE_COLORS.actionScript}>
      <StandardNodeHeader
        expandable
        menuActions={menuActions}
        subtitle="Script task"
        title="Run inventory synchronization"
      />
      <NodeBody>
        <Content component={ContentVariants.small}>Collect inventory from the selected managed hosts.</Content>
      </NodeBody>
      <NodeSidePanel>
        <StackItem>
          <Content component={ContentVariants.small}>Credentials: automation-admin</Content>
        </StackItem>
      </NodeSidePanel>
    </NodeComponent>
  ),
}

/** Selection uses an outline without changing the node's box geometry. */
export const Selected: Story = {
  render: () => (
    <NodeComponent
      nodeProps={createNodeProps({ id: 'selected', selected: true })}
      topBarColor={NODE_TYPE_COLORS.actionScript}
    >
      <StandardNodeHeader
        expandable
        menuActions={menuActions}
        subtitle="Script task"
        title="Run inventory synchronization"
      />
      <NodeBody>
        <Content component={ContentVariants.small}>
          The selected node keeps its normal type indicator and content.
        </Content>
      </NodeBody>
    </NodeComponent>
  ),
}

/** Disabled and validation-error states combine the production data flags with representative node content. */
export const DisabledAndValidationError: Story = {
  render: () => (
    <div className={styles.comparisonGrid}>
      <NodeComponent
        nodeProps={createNodeProps({ id: 'disabled', data: { settings: { disabled: true } } })}
        topBarColor={NODE_TYPE_COLORS.actionScript}
      >
        <NodeHeader>
          <NodeExpandToggle />
          <NodeTitle title="Disabled deployment" subTitle="Script task" />
        </NodeHeader>
        <NodeBody>
          <Content component={ContentVariants.small}>This step will be skipped when the workflow runs.</Content>
        </NodeBody>
      </NodeComponent>
      <NodeComponent
        nodeProps={createNodeProps({ id: 'validation', data: { __validationError: true } })}
        topBarColor={NODE_TYPE_COLORS.logic}
      >
        <NodeHeader>
          <NodeExpandToggle />
          <NodeTitle title="Check deployment policy" subTitle="Condition" />
        </NodeHeader>
        <NodeBody>
          <Content component={ContentVariants.small}>The condition needs a valid expression before it can run.</Content>
        </NodeBody>
      </NodeComponent>
    </div>
  ),
}

/** Every contract-supported execution status, including a retry count for the retrying state. */
export const ExecutionStates: Story = {
  parameters: { storyCanvas: { height: '40rem' } },
  render: () => (
    <div className={styles.gallery}>
      {executionStatuses.map((status) => (
        <NodeExample key={status} label={status}>
          <NodeComponent
            nodeProps={createNodeProps({ id: `execution-${status}`, name: `${status} task` })}
            executionState={{ status, retry_count: status === ACTIVITY_STATUS.RETRYING ? 2 : undefined }}
            topBarColor={NODE_TYPE_COLORS.actionScript}
          >
            <NodeHeader>
              <NodeTitle title={`${status} task`} subTitle="Script task" />
            </NodeHeader>
            <NodeBody>
              <Content component={ContentVariants.small}>Execution badge shown below the node.</Content>
            </NodeBody>
          </NodeComponent>
        </NodeExample>
      ))}
    </div>
  ),
}

/** Expanded and collapsed states use the same production expand-toggle interaction. */
export const CollapsedAndExpanded: Story = {
  render: () => (
    <div className={styles.comparisonGrid}>
      <NodeComponent nodeProps={createNodeProps({ id: 'expanded' })} topBarColor={NODE_TYPE_COLORS.actionScript}>
        <NodeHeader>
          <NodeExpandToggle />
          <NodeTitle title="Expanded node" subTitle="Script task" />
        </NodeHeader>
        <NodeBody>
          <Content component={ContentVariants.small}>
            The body is visible initially and may be collapsed with the caret.
          </Content>
        </NodeBody>
      </NodeComponent>
      <NodeComponent nodeProps={createNodeProps({ id: 'collapsed' })} topBarColor={NODE_TYPE_COLORS.actionScript}>
        <NodeHeader>
          <NodeExpandToggle />
          <NodeTitle title="Collapsed node" subTitle="Script task" />
        </NodeHeader>
        <NodeBody>
          <Content component={ContentVariants.small}>This body appears after expanding the node.</Content>
        </NodeBody>
      </NodeComponent>
    </div>
  ),
  play: async ({ canvas }) => {
    const [, collapsedToggle] = canvas.getAllByRole('button', { name: 'Collapse step details' })
    if (collapsedToggle) await userEvent.click(collapsedToggle)
  },
}

/** The menu begins closed; open it to inspect normal, icon, separated, and danger actions. */
export const Menu: Story = {
  render: () => (
    <NodeComponent nodeProps={createNodeProps({ id: 'menu' })} topBarColor={NODE_TYPE_COLORS.actionScript}>
      <StandardNodeHeader expandable menuActions={menuActions} subtitle="Script task" title="Node action menu" />
      <NodeBody>
        <Content component={ContentVariants.small}>Use the kebab button to open the node actions.</Content>
      </NodeBody>
    </NodeComponent>
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
        <NodeComponent nodeProps={createNodeProps({ id: 'default-width' })} topBarColor={NODE_TYPE_COLORS.actionScript}>
          <NodeHeader>
            <NodeTitle title="Default task" subTitle="Script" />
          </NodeHeader>
        </NodeComponent>
      </NodeExample>
      <NodeExample label="Generic node (360 px)">
        <NodeComponent
          nodeProps={createNodeProps({ id: 'generic-width', type: FlowNodeType.GENERIC })}
          hasDashedBorder
          topBarColor={NODE_TYPE_COLORS.generic}
        >
          <NodeHeader>
            <NodeTitle title="Generic placeholder" subTitle="Add a step" />
          </NodeHeader>
        </NodeComponent>
      </NodeExample>
      <NodeExample label="Agentic task (360 px)">
        <NodeComponent
          nodeProps={createNodeProps({
            id: 'agentic-width',
            data: { type: ExecutorTypeEnum.AGENTIC, name: 'Agentic investigation' },
          })}
          topBarColor={NODE_TYPE_COLORS.actionAgentic}
        >
          <NodeHeader>
            <NodeTitle title="Agentic investigation" subTitle="Agentic task" />
          </NodeHeader>
        </NodeComponent>
      </NodeExample>
    </div>
  ),
}

/** Handle configurations are shown together because they alter the canvas connection affordances. */
export const Handles: Story = {
  render: () => (
    <div className={styles.gallery}>
      <NodeExample label="Default source and target">
        <NodeComponent nodeProps={createNodeProps({ id: 'handles-default' })} topBarColor={NODE_TYPE_COLORS.logic}>
          <NodeHeader>
            <NodeTitle title="Default handles" />
          </NodeHeader>
        </NodeComponent>
      </NodeExample>
      <NodeExample label="Reversed handles">
        <NodeComponent
          nodeProps={createNodeProps({ id: 'handles-reversed' })}
          reverseHandles
          topBarColor={NODE_TYPE_COLORS.logic}
        >
          <NodeHeader>
            <NodeTitle title="Reversed handles" />
          </NodeHeader>
        </NodeComponent>
      </NodeExample>
      <NodeExample label="Start and end handles">
        <NodeComponent
          nodeProps={createNodeProps({ id: 'handles-start-end' })}
          enableStart
          enableEnd
          topBarColor={NODE_TYPE_COLORS.logic}
        >
          <NodeHeader>
            <NodeTitle title="Start and end handles" />
          </NodeHeader>
        </NodeComponent>
      </NodeExample>
      <NodeExample label="Source and target disabled">
        <NodeComponent
          nodeProps={createNodeProps({ id: 'handles-disabled' })}
          disableSource
          disableTarget
          topBarColor={NODE_TYPE_COLORS.logic}
        >
          <NodeHeader>
            <NodeTitle title="No connection handles" />
          </NodeHeader>
        </NodeComponent>
      </NodeExample>
    </div>
  ),
}

/** Fixed visual inventory for global-node states. Menus remain closed so no popover obscures adjacent nodes. */
export const KitchenSink: Story = {
  parameters: { storyCanvas: { height: '80rem' } },
  render: () => <KitchenSinkGallery />,
  play: async ({ canvas }) => {
    const [, collapsedToggle] = canvas.getAllByRole('button', { name: 'Collapse step details' })
    if (collapsedToggle) await userEvent.click(collapsedToggle)
  },
}
