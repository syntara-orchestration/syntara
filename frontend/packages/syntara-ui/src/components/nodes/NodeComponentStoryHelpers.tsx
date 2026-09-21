import { Content, ContentVariants, Flex, FlexItem, Stack, StackItem, Title, TitleSizes } from '@patternfly/react-core'
import { RhUiDuplicateIcon, RhUiPlayIcon, RhUiTrashIcon, RhUiWarningFillIcon } from '@patternfly/react-icons'
import { ExecutorTypeEnum } from '@syntara/contracts'
import { Position, type NodeProps } from '@xyflow/react'

import { FlowNodeType } from '../../constants'
import { ACTIVITY_STATUS } from '../../routes/builder/utils/executionState/executionHelpers'
import { NODE_TYPE_COLORS } from '../../routes/workflows/canvas/nodeTypeColors'

import { NodeBody } from './NodeBody'
import { NodeComponent } from './NodeComponent'
import styles from './NodeComponent.stories.module.css'
import { NodeExpandToggle } from './NodeExpandToggle'
import { NodeHeader } from './NodeHeader'
import { NodeMenu } from './NodeMenu'
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

type KitchenNode = {
  label: string
  nodeProps: NodeProps
  nodeOptions?: Omit<React.ComponentProps<typeof NodeComponent>, 'children' | 'nodeProps'>
  title?: string
  subTitle?: string
  expandable?: boolean
  menu?: boolean
  body?: React.ReactNode
  sidePanel?: boolean
}

const menuActions = [
  { id: 'run', label: 'Run step', onClick: () => undefined, icon: <RhUiPlayIcon /> },
  { id: 'duplicate', label: 'Duplicate', onClick: () => undefined, icon: <RhUiDuplicateIcon /> },
  { id: 'separator', label: '', onClick: () => undefined, separator: true },
  { id: 'delete', label: 'Delete', onClick: () => undefined, icon: <RhUiTrashIcon />, variant: 'danger' as const },
]

function createNodeProps(options: {
  id: string
  selected?: boolean
  type?: string
  data?: Partial<StoryNodeData>
}): NodeProps {
  const type = options.type ?? FlowNodeType.TASK
  return {
    id: options.id,
    data: { id: options.id, name: options.id, type, ...options.data },
    selected: options.selected ?? false,
    type,
    dragging: false,
    zIndex: 0,
    positionAbsoluteX: 0,
    positionAbsoluteY: 0,
    isConnectable: true,
    sourcePosition: Position.Right,
    targetPosition: Position.Left,
  } as unknown as NodeProps
}

const executionNodes: KitchenNode[] = Object.values(ACTIVITY_STATUS).map((status) => ({
  label: `${status} execution state`,
  nodeProps: createNodeProps({ id: `kitchen-${status}` }),
  nodeOptions: {
    executionState: { status, retry_count: status === ACTIVITY_STATUS.RETRYING ? 2 : undefined },
    topBarColor: NODE_TYPE_COLORS.actionScript,
  },
  title: `${status} task`,
}))

const kitchenNodes: KitchenNode[] = [
  {
    label: 'Full composition',
    nodeProps: createNodeProps({ id: 'base' }),
    nodeOptions: { topBarColor: NODE_TYPE_COLORS.actionScript },
    title: 'Run inventory synchronization',
    subTitle: 'Script task',
    expandable: true,
    menu: true,
    body: 'Collect inventory from managed hosts.',
    sidePanel: true,
  },
  {
    label: 'Selected dashed placeholder',
    nodeProps: createNodeProps({ id: 'selected-dashed', selected: true, type: FlowNodeType.GENERIC }),
    nodeOptions: { hasDashedBorder: true },
    title: 'Selected placeholder',
  },
  {
    label: 'Disabled validation error with mock data pinned',
    nodeProps: createNodeProps({
      id: 'disabled-invalid',
      data: { settings: { disabled: true }, __validationError: true, metadata: { __mockDataPinned: true } },
    }),
    nodeOptions: { topBarColor: NODE_TYPE_COLORS.logic },
    title: 'Invalid pinned condition',
  },
  {
    label: 'Collapsed content',
    nodeProps: createNodeProps({ id: 'collapsed' }),
    nodeOptions: { initiallyExpanded: false, topBarColor: NODE_TYPE_COLORS.actionScript },
    title: 'Collapsed task',
    expandable: true,
    body: 'Hidden until expanded.',
  },
  {
    label: 'Generic wide node',
    nodeProps: createNodeProps({ id: 'generic', type: FlowNodeType.GENERIC }),
    nodeOptions: { hasDashedBorder: true },
    title: 'Generic placeholder',
  },
  {
    label: 'Agentic wide task',
    nodeProps: createNodeProps({ id: 'agentic', data: { type: ExecutorTypeEnum.AGENTIC } }),
    nodeOptions: { topBarColor: NODE_TYPE_COLORS.actionAgentic },
    title: 'Agentic task',
  },
  {
    label: 'Reversed start and end handles',
    nodeProps: createNodeProps({ id: 'handles' }),
    nodeOptions: { reverseHandles: true, enableStart: true, enableEnd: true, topBarColor: NODE_TYPE_COLORS.logic },
    title: 'Branch handles',
  },
  {
    label: 'No source or target handle',
    nodeProps: createNodeProps({ id: 'no-handles' }),
    nodeOptions: { disableSource: true, disableTarget: true, topBarColor: NODE_TYPE_COLORS.logic },
    title: 'No handles',
  },
  {
    label: 'Subtitle-only title',
    nodeProps: createNodeProps({ id: 'subtitle' }),
    nodeOptions: { topBarColor: NODE_TYPE_COLORS.logic },
    subTitle: 'Fallback title from subtitle',
  },
]

function KitchenNodeExample({ node }: Readonly<{ node: KitchenNode }>) {
  return (
    <div className={styles.nodeExample}>
      <Content component={ContentVariants.small} className={styles.nodeLabel}>
        {node.label}
      </Content>
      <NodeComponent nodeProps={node.nodeProps} {...node.nodeOptions}>
        <NodeHeader>
          {node.expandable && <NodeExpandToggle />}
          <NodeTitle title={node.title} subTitle={node.subTitle} />
          {node.menu && <NodeMenu menuActions={menuActions} />}
        </NodeHeader>
        {node.body && (
          <NodeBody>
            <Content component={ContentVariants.small}>{node.body}</Content>
          </NodeBody>
        )}
        {node.sidePanel && (
          <NodeSidePanel>
            <StackItem>
              <Content component={ContentVariants.small}>Credentials: automation-admin</Content>
            </StackItem>
          </NodeSidePanel>
        )}
      </NodeComponent>
    </div>
  )
}

export function KitchenSinkGallery() {
  return (
    <Stack hasGutter>
      <StackItem>
        <Title headingLevel="h2" size={TitleSizes.lg}>
          Global node state inventory
        </Title>
      </StackItem>
      <StackItem>
        <div className={styles.gallery}>
          {[...kitchenNodes, ...executionNodes].map((node) => (
            <KitchenNodeExample key={node.label} node={node} />
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
