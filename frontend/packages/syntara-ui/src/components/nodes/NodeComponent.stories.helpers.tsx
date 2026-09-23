import { Content, ContentVariants } from '@patternfly/react-core'
import { RhUiDuplicateIcon, RhUiPlayIcon, RhUiTrashIcon } from '@patternfly/react-icons'
import type { Node, NodeProps } from '@xyflow/react'
import { Background, BackgroundVariant, Position, ReactFlow } from '@xyflow/react'
import { useCallback, useState, type ReactNode } from 'react'

import { FlowNodeType } from '../../constants'
import { ACTIVITY_STATUS } from '../../routes/builder/utils/executionState/executionHelpers'

import styles from './NodeComponent.stories.module.css'

/** Shared inert actions for stories that demonstrate a node header's action menu. */
export const MENU_ACTIONS = [
  { id: 'run', label: 'Run step', onClick: () => undefined, icon: <RhUiPlayIcon /> },
  { id: 'duplicate', label: 'Duplicate', onClick: () => undefined, icon: <RhUiDuplicateIcon /> },
  { id: 'separator', label: '', onClick: () => undefined, separator: true },
  { id: 'delete', label: 'Delete', onClick: () => undefined, icon: <RhUiTrashIcon />, variant: 'danger' as const },
]

export const EXECUTION_STATES = Object.values(ACTIVITY_STATUS).map((status) => ({
  status,
  retry_count: status === ACTIVITY_STATUS.RETRYING ? 2 : undefined,
}))

/** Minimal workflow data used to render `NodeComponent` states outside a builder canvas. */
export type StoryNodeData = Record<string, unknown> & {
  id: string
  name: string
  type: string
  __validationError?: boolean
  metadata?: { __mockDataPinned?: boolean }
  settings?: { disabled?: boolean }
}

/** Values that vary between otherwise complete React Flow node fixtures. */
export type NodePropsOptions = {
  id: string
  name?: string
  selected?: boolean
  type?: string
  data?: Partial<StoryNodeData>
}

/** Creates the complete set of React Flow props required by `NodeComponent` in a Storybook story. */
export function createNodeProps(options: NodePropsOptions): NodeProps<Node<StoryNodeData>> {
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
    selectable: true,
    deletable: true,
    draggable: true,
    positionAbsoluteX: 0,
    positionAbsoluteY: 0,
    isConnectable: true,
    sourcePosition: Position.Right,
    targetPosition: Position.Left,
  }
}

type StoryCanvasNode = Node<{ content: ReactNode; onContentResize: (height: number) => void }, 'storybook'>

function StoryCanvasNodeComponent(props: NodeProps<StoryCanvasNode>) {
  const contentRef = useCallback(
    (element: HTMLDivElement | null) => {
      if (!element) return

      const reportHeight = () => props.data.onContentResize(element.offsetHeight)
      const observer = new ResizeObserver(reportHeight)
      reportHeight()
      observer.observe(element)
      return () => observer.disconnect()
    },
    [props.data]
  )

  return <div ref={contentRef}>{props.data.content}</div>
}

const STORY_CANVAS_NODE_TYPES = { storybook: StoryCanvasNodeComponent }

/** Renders a stable React Flow canvas around node stories so their handles and canvas styles are visible. */
export function NodeStoryCanvas({
  children,
  minimumHeight = 512,
}: Readonly<{ children: ReactNode; minimumHeight?: number }>) {
  const [height, setHeight] = useState(minimumHeight)
  const onContentResize = useCallback(
    (contentHeight: number) => setHeight(Math.max(minimumHeight, contentHeight + 128)),
    [minimumHeight]
  )

  return (
    <div className={styles.storyCanvas} style={{ height }}>
      <ReactFlow
        defaultViewport={{ x: 0, y: 0, zoom: 1 }}
        nodes={[
          {
            id: 'storybook-node',
            type: 'storybook',
            position: { x: 64, y: 64 },
            data: { content: children, onContentResize },
            style: { width: 'calc(100% - 9rem)' },
          },
        ]}
        nodeTypes={STORY_CANVAS_NODE_TYPES}
        nodesConnectable
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

/** Adds a concise visible label to an individual state in a node-story gallery. */
export function NodeExample({
  label,
  children,
  testId,
}: Readonly<{ label: string; children: ReactNode; testId?: string }>) {
  return (
    <div className={styles.nodeExample} data-testid={testId}>
      <Content component={ContentVariants.small} className={styles.nodeLabel}>
        {label}
      </Content>
      {children}
    </div>
  )
}
