import { Flex, FlexItem } from '@patternfly/react-core'
import type { Node } from '@xyflow/react'
import { memo } from 'react'

import { useDocLink } from '../../../utils/docs/useDocLink'
import type { NodeType } from '../../workflows/canvas/nodes/NodeType'
import { StepDetailsPanel } from '../StepDetailsPanel'
import type { WorkflowMetadata } from '../types/workflowMetadata'
import { resolveStepDocKey } from '../utils/resolveStepDocKey'
import { useIsVersionView } from '../VersionViewContext'

type StepEditorOverlayProps = {
  isOpen: boolean
  mode: 'add' | 'edit' | null
  selectedNode: Node<NodeType['data']> | null
  stepTypeId: string | null
  stepSubtypeId: string | null
  sourceNodeId: string | null
  replacementNodeId: string | null
  executionId?: string | null
  workflowId?: string | null
  onConnect: (sourceId: string, targetId: string) => void
  onClose: () => void
  projectId?: string
  onNavigateToStep?: (nodeId: string) => void
  onAddStep?: (sourceNodeId: string, sourceHandle?: string) => void
  workflowMetadata?: WorkflowMetadata
  onRunStep?: () => void
  onStepAdded?: () => void
}

export const StepEditorOverlay = memo(function StepEditorOverlay(props: StepEditorOverlayProps) {
  const isVersionView = useIsVersionView()
  const {
    isOpen,
    mode,
    selectedNode,
    stepTypeId,
    stepSubtypeId,
    sourceNodeId,
    replacementNodeId,
    executionId,
    workflowId,
    onConnect,
    onClose,
    projectId,
    onNavigateToStep,
    onAddStep,
    workflowMetadata,
    onRunStep,
    onStepAdded,
  } = props

  const stepDocKey = resolveStepDocKey({ mode, stepTypeId, stepSubtypeId, selectedNode })
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
        <StepDetailsPanel
          mode={mode === 'edit' ? 'edit' : 'add'}
          node={mode === 'edit' ? (selectedNode ?? undefined) : undefined}
          stepTypeId={mode === 'add' ? stepTypeId : null}
          stepSubtypeId={mode === 'add' ? stepSubtypeId : null}
          sourceNodeId={sourceNodeId}
          replacementNodeId={replacementNodeId}
          executionId={executionId}
          workflowId={workflowId}
          onConnect={onConnect}
          onClose={onClose}
          projectId={projectId}
          onNavigateToStep={onNavigateToStep}
          onAddStep={onAddStep}
          docLink={stepDocLink}
          workflowMetadata={workflowMetadata}
          onRunStep={isVersionView ? undefined : onRunStep}
          readOnly={isVersionView}
          onStepAdded={onStepAdded}
        />
      </FlexItem>
    </Flex>
  )
})
