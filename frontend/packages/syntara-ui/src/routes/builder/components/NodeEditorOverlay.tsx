import { Flex, FlexItem } from '@patternfly/react-core'
import type { Node } from '@xyflow/react'
import { memo } from 'react'

import { useDocLink } from '../../../utils/docs/useDocLink'
import type { NodeType } from '../../workflows/canvas/nodes/NodeType'
import { NodeDetailsPanel } from '../NodeDetailsPanel'
import type { WorkflowMetadata } from '../types/workflowMetadata'
import { resolveStepDocKey } from '../utils/resolveStepDocKey'
import { useIsVersionView } from '../VersionViewContext'

type NodeEditorOverlayProps = {
  isOpen: boolean
  mode: 'add' | 'edit' | null
  selectedNode: Node<NodeType['data']> | null
  nodeTypeId: string | null
  nodeSubtypeId: string | null
  sourceNodeId: string | null
  replacementNodeId: string | null
  executionId?: string | null
  workflowId?: string | null
  onConnect: (sourceId: string, targetId: string) => void
  onClose: () => void
  projectId?: string
  onNavigateToNode?: (nodeId: string) => void
  onAddStep?: (sourceNodeId: string, sourceHandle?: string) => void
  workflowMetadata?: WorkflowMetadata
  onRunStep?: () => void
  onNodeAdded?: () => void
}

export const NodeEditorOverlay = memo(function NodeEditorOverlay(props: NodeEditorOverlayProps) {
  const isVersionView = useIsVersionView()
  const {
    isOpen,
    mode,
    selectedNode,
    nodeTypeId,
    nodeSubtypeId,
    sourceNodeId,
    replacementNodeId,
    executionId,
    workflowId,
    onConnect,
    onClose,
    projectId,
    onNavigateToNode,
    onAddStep,
    workflowMetadata,
    onRunStep,
    onNodeAdded,
  } = props

  const stepDocKey = resolveStepDocKey({ mode, nodeTypeId, nodeSubtypeId, selectedNode })
  // Hook must run unconditionally; ignore the result when this step has no docs.
  const resolvedDocLink = useDocLink(stepDocKey ?? 'builder')
  const stepDocLink = stepDocKey === null ? undefined : resolvedDocLink

  if (!isOpen) return null

  return (
    <Flex
      style={{
        position: 'absolute',
        inset: 0,
        zIndex: 2,
      }}
    >
      <FlexItem grow={{ default: 'grow' }} style={{ minWidth: 0, height: '100%' }}>
        <NodeDetailsPanel
          mode={mode === 'edit' ? 'edit' : 'add'}
          node={mode === 'edit' ? (selectedNode ?? undefined) : undefined}
          nodeTypeId={mode === 'add' ? nodeTypeId : null}
          nodeSubtypeId={mode === 'add' ? nodeSubtypeId : null}
          sourceNodeId={sourceNodeId}
          replacementNodeId={replacementNodeId}
          executionId={executionId}
          workflowId={workflowId}
          onConnect={onConnect}
          onClose={onClose}
          projectId={projectId}
          onNavigateToNode={onNavigateToNode}
          onAddStep={onAddStep}
          docLink={stepDocLink}
          workflowMetadata={workflowMetadata}
          onRunStep={isVersionView ? undefined : onRunStep}
          readOnly={isVersionView}
          onNodeAdded={onNodeAdded}
        />
      </FlexItem>
    </Flex>
  )
})
