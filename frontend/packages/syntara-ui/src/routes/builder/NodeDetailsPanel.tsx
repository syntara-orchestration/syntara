import { Button, Flex } from '@patternfly/react-core'
import type {
  ConditionActivity,
  ConvergeActivity,
  LoopActivity,
  SwitchActivity,
  TaskActivity,
  WaitActivity,
} from '@syntara/contracts'
import { ExecutorTypeEnum } from '@syntara/contracts'
import type { Node } from '@xyflow/react'
import type { ReactNode } from 'react'
import { useState } from 'react'

import { FlowNodeType, RegistryNodeId } from '../../constants'
import { useAlerts } from '../../providers/alerts'
import {
  useWorkflowStore,
  useWorkflowStoreActions,
  selectCurrentWorkflow,
  getActivityMetadata,
  type Activity,
  type ActivityMetadata,
} from '../../stores/useWorkflowStore'
import { parseTriggerIndex } from '../../utils/triggerNodeIds'
import { NodeMenu } from '../workflows/canvas/nodes/common/NodeMenu'
import {
  MenuNodeType,
  type MenuNodeTypeUnion,
  useNodeMenuActions,
} from '../workflows/canvas/nodes/hooks/useNodeMenuActions'
import type { NodeType } from '../workflows/canvas/nodes/NodeType'
import { renderNodeIcon } from '../workflows/canvas/nodes/renderNodeIcon'

import {
  ApprovalNodeDetails,
  ConditionNodeDetails,
  ConvergeNodeDetails,
  LoopNodeDetails,
  SwitchNodeDetails,
  TaskNodeDetails,
  TriggerNodeDetails,
  WaitNodeDetails,
} from './node-details'
import { NodeEditorLayout } from './NodeEditorLayout'
import { NodeRawDataView } from './NodeRawDataView'
import { NodeRegistry } from './registry/NodeRegistry'
import type { WorkflowMetadata } from './types/workflowMetadata'
import { resolveIconForNode, resolveIconForType } from './utils/nodeIcons'
import { getDefaultNodeBaseName, getNodeDisplayName } from './utils/nodeNaming'
import { buildPanelMenuActions } from './utils/panelMenuActions'

/**
 * IMPORTANT: When adding a new step type, ensure the corresponding NodeDetails component
 * calls onClose() after successfully updating the step. This ensures the side panel
 * closes automatically after modifications.
 */

/**
 * Remove __isGeneric from already-sanitized metadata.
 * SECURITY: Input MUST be pre-sanitized by getActivityMetadata().
 * This function only removes __isGeneric; it does NOT enforce the allowlist.
 */
function cleanMetadata(metadata: ActivityMetadata | undefined): ActivityMetadata | undefined {
  if (!metadata) return undefined
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const { __isGeneric: _isGeneric, ...rest } = metadata
  return Object.keys(rest).length > 0 ? (rest as ActivityMetadata) : undefined
}

/** Get formId for add mode based on node type and subtype */
function getAddModeFormId(
  nodeTypeId: string | null | undefined,
  nodeSubtypeId: string | null | undefined
): string | undefined {
  // Simple node types without subtypes
  const simpleFormMap: Record<string, string> = {
    [RegistryNodeId.TRIGGER]: 'trigger-node-form',
    [RegistryNodeId.ACTION]: 'action-node-form',
    [RegistryNodeId.AGENT]: 'ai-agent-node-form',
    [RegistryNodeId.APPROVAL]: 'approval-node-form',
  }
  if (nodeTypeId && nodeTypeId in simpleFormMap) return simpleFormMap[nodeTypeId]

  // Logic node subtypes
  if (nodeTypeId === RegistryNodeId.LOGIC && nodeSubtypeId) {
    const logicFormMap: Record<string, string> = {
      [RegistryNodeId.LOGIC_CONDITION]: 'condition-node-form',
      [RegistryNodeId.LOGIC_LOOP]: 'loop-node-form',
      [RegistryNodeId.LOGIC_CONVERGE]: 'converge-node-form',
      [RegistryNodeId.LOGIC_SWITCH]: 'switch-node-form',
      [RegistryNodeId.LOGIC_WAIT]: 'wait-node-form',
    }
    return logicFormMap[nodeSubtypeId]
  }

  // AAP Execution node subtypes
  if (nodeTypeId === RegistryNodeId.AAP_EXECUTION && nodeSubtypeId) {
    const aapFormMap: Record<string, string> = {
      [RegistryNodeId.AAP_JOB_TEMPLATE]: 'aap-job-template-form',
      [RegistryNodeId.AAP_WORKFLOW_TEMPLATE]: 'aap-workflow-template-form',
    }
    return aapFormMap[nodeSubtypeId]
  }

  return undefined
}

/** Get formId for TASK nodes by checking executor type */
function getTaskFormId(taskData: TaskActivity): string {
  const executor = taskData.type

  // Check if it's an AAP job template task
  if (executor === ExecutorTypeEnum.AAP_JOB_TEMPLATE) {
    return 'aap-job-template-form'
  }

  // Check if it's an AAP workflow template task
  if (executor === ExecutorTypeEnum.AAP_WORKFLOW_JOB_TEMPLATE) {
    return 'aap-workflow-template-form'
  }

  // Check if it's an AI Agent task
  if (executor === ExecutorTypeEnum.AGENTIC) {
    return 'ai-agent-node-form'
  }

  // Script or HTTP request
  if (executor === ExecutorTypeEnum.SCRIPT || executor === ExecutorTypeEnum.HTTP_REQUEST) {
    return 'action-node-form'
  }

  return 'action-node-form' // Default fallback
}

/** Get formId for edit mode based on node type */
function getEditModeFormId(node: Node<NodeType['data']> | undefined): string | undefined {
  if (!node) return undefined
  if (node.type === FlowNodeType.TRIGGER) return 'trigger-node-form'
  if (node.type === FlowNodeType.CONDITION) return 'condition-node-form'
  if (node.type === FlowNodeType.LOOP) return 'loop-node-form'
  if (node.type === FlowNodeType.CONVERGE) return 'converge-node-form'
  if (node.type === FlowNodeType.WAIT) return 'wait-node-form'
  if (node.type === FlowNodeType.APPROVAL) return 'approval-node-form'
  if (node.type === FlowNodeType.SWITCH) return 'switch-node-form'
  if (node.type === FlowNodeType.TASK) {
    return getTaskFormId(node.data as TaskActivity)
  }
  return undefined
}

const CONTROL_FLOW_TYPES: ReadonlySet<string> = new Set([
  FlowNodeType.CONDITION,
  FlowNodeType.LOOP,
  FlowNodeType.CONVERGE,
  FlowNodeType.SWITCH,
  FlowNodeType.WAIT,
])

function resolveMenuNodeType(flowNodeType: string | undefined): MenuNodeTypeUnion {
  if (flowNodeType === FlowNodeType.TRIGGER) return MenuNodeType.TRIGGER
  if (flowNodeType && CONTROL_FLOW_TYPES.has(flowNodeType)) return MenuNodeType.CONTROL_FLOW
  return MenuNodeType.ACTIVITY
}

function getNodeDisabledState(node: Node<NodeType['data']> | undefined): boolean {
  const nodeData = node?.data as Record<string, unknown> | undefined
  const nodeSettings = nodeData?.settings as { disabled?: boolean } | undefined
  return nodeSettings?.disabled ?? false
}

/** Top-level search is correct: the builder store always holds a flat activity list (see WorkflowTransform). */
function findActivityInCurrentWorkflow(activityId: string): Activity | undefined {
  const current = useWorkflowStore.getState().currentWorkflow
  return current?.workflow.activities.find((activity: Activity) => activity.id === activityId)
}

/** Renders the appropriate details component for a given node in edit mode. */
function renderEditModeContent(
  node: Node<NodeType['data']>,
  currentWorkflow: ReturnType<typeof selectCurrentWorkflow>,
  onClose: () => void,
  onHeaderContentChange: (content: ReactNode | null) => void,
  projectId?: string
): ReactNode {
  if (node.type === FlowNodeType.TRIGGER) {
    const triggerIdx = parseTriggerIndex(node.id) ?? 0
    const trigger = currentWorkflow?.triggers?.[triggerIdx]
    if (trigger) {
      return (
        <TriggerNodeDetails
          trigger={trigger}
          triggerIndex={triggerIdx}
          onClose={onClose}
          onHeaderContentChange={onHeaderContentChange}
        />
      )
    }
  }

  if (node.type === FlowNodeType.TASK) {
    return (
      <TaskNodeDetails
        taskData={node.data as TaskActivity}
        nodeId={node.id}
        onClose={onClose}
        onHeaderContentChange={onHeaderContentChange}
        projectId={projectId}
      />
    )
  }

  if (node.type === FlowNodeType.APPROVAL) {
    return (
      <ApprovalNodeDetails
        taskData={node.data as TaskActivity}
        nodeId={node.id}
        onClose={onClose}
        onHeaderContentChange={onHeaderContentChange}
        projectId={projectId}
      />
    )
  }

  if (node.type === FlowNodeType.CONDITION) {
    return (
      <ConditionNodeDetails
        conditionData={node.data as ConditionActivity}
        nodeId={node.id}
        onClose={onClose}
        onHeaderContentChange={onHeaderContentChange}
      />
    )
  }

  if (node.type === FlowNodeType.LOOP) {
    return (
      <LoopNodeDetails
        loopData={node.data as LoopActivity}
        nodeId={node.id}
        onClose={onClose}
        onHeaderContentChange={onHeaderContentChange}
      />
    )
  }

  if (node.type === FlowNodeType.CONVERGE) {
    return (
      <ConvergeNodeDetails
        convergeData={node.data as ConvergeActivity}
        nodeId={node.id}
        onClose={onClose}
        onHeaderContentChange={onHeaderContentChange}
      />
    )
  }

  if (node.type === FlowNodeType.SWITCH) {
    return (
      <SwitchNodeDetails
        switchData={node.data as SwitchActivity}
        nodeId={node.id}
        onClose={onClose}
        onHeaderContentChange={onHeaderContentChange}
      />
    )
  }

  if (node.type === FlowNodeType.WAIT) {
    return (
      <WaitNodeDetails
        waitData={node.data as WaitActivity}
        nodeId={node.id}
        onClose={onClose}
        onHeaderContentChange={onHeaderContentChange}
      />
    )
  }

  return <NodeRawDataView node={node} />
}

type NodeDetailsPanelProps = {
  mode: 'add' | 'edit'
  node?: Node<NodeType['data']>
  nodeTypeId?: string | null
  nodeSubtypeId?: string | null
  sourceNodeId?: string | null
  replacementNodeId?: string | null
  executionId?: string | null
  workflowId?: string | null
  onConnect?: (sourceId: string, targetId: string) => void
  onClose: () => void
  projectId?: string
  onNavigateToNode?: (nodeId: string) => void
  onAddStep?: (sourceNodeId: string, sourceHandle?: string) => void
  docLink?: string
  workflowMetadata?: WorkflowMetadata
  onRunStep?: () => void
  readOnly?: boolean
  onNodeAdded?: () => void
}

function createAddStepHandler(
  nodeId: string | undefined,
  onAddStep: ((sourceNodeId: string, sourceHandle?: string) => void) | undefined
): ((handle?: string) => void) | undefined {
  if (!nodeId || !onAddStep) return undefined
  return (handle?: string) => onAddStep(nodeId, handle)
}

export function NodeDetailsPanel(props: NodeDetailsPanelProps) {
  const {
    mode,
    node,
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
    onRunStep,
    readOnly,
    onNodeAdded,
  } = props
  const { showError } = useAlerts()
  // Use typed selector for optimized subscription
  const currentWorkflow = useWorkflowStore(selectCurrentWorkflow)
  const [headerContent, setHeaderContent] = useState<ReactNode | null>(null)
  // Use action accessor - component won't re-render when store state changes
  const { moveActivityAfter, updateActivity, replaceActivity, removeActivity } = useWorkflowStoreActions()
  const nodeId = node?.id
  const isTriggerNode = node?.type === FlowNodeType.TRIGGER
  const triggerIndex = isTriggerNode ? parseTriggerIndex(nodeId ?? '') : undefined
  const menuNodeType = resolveMenuNodeType(node?.type)
  const nodeAddStepHandler = createAddStepHandler(nodeId, onAddStep)
  const menuActions = useNodeMenuActions({
    nodeId: nodeId ?? 'unknown',
    nodeType: menuNodeType,
    triggerIndex: isTriggerNode ? triggerIndex : undefined,
    disabled: getNodeDisabledState(node),
  })
  const panelMenuActions = buildPanelMenuActions(mode, node, menuActions, onClose)
  const headerActions = panelMenuActions.length > 0 ? <NodeMenu menuActions={panelMenuActions} /> : null

  const iconDescriptor =
    mode === 'edit' && node
      ? resolveIconForNode(node, currentWorkflow)
      : resolveIconForType({ nodeTypeId, nodeSubtypeId })
  const headerIcon = renderNodeIcon(iconDescriptor.icon, iconDescriptor.id, 'header')

  const renderContent = () => {
    if (mode === 'add') {
      const selectedNode = nodeTypeId ? NodeRegistry.get(nodeTypeId) : null
      const selectedSubtype = selectedNode?.subtypes?.find((subtype) => subtype.id === nodeSubtypeId) ?? null

      if (!selectedNode) return null

      const initialData = {
        ...(selectedSubtype?.initialData ?? {}),
      } as Record<string, unknown>

      initialData.name ??= getNodeDisplayName(
        getDefaultNodeBaseName({
          nodeTypeId: selectedNode.id,
          nodeSubtypeId: selectedSubtype?.id,
          initialData,
          label: selectedSubtype?.label ?? selectedNode.label,
        })
      )

      // For nodes with subtypes, use the subtype's form component
      const FormComponent = selectedSubtype?.formComponent ?? selectedNode.formComponent
      const subtypeFormProps = selectedSubtype?.formProps ?? {}
      const submitButtonText = 'Add step'

      /** Returns true if replacement succeeded, false if lookup failed. */
      const handleReplacement = (newNodeId: string | undefined): boolean => {
        if (!replacementNodeId) return false

        if (newNodeId) {
          const newActivity = findActivityInCurrentWorkflow(newNodeId)
          if (!newActivity) return false

          removeActivity(newNodeId)
          const cleaned = cleanMetadata(getActivityMetadata(newActivity))
          replaceActivity(replacementNodeId, {
            ...newActivity,
            id: replacementNodeId,
            metadata: cleaned,
          })
        } else {
          const genericActivity = findActivityInCurrentWorkflow(replacementNodeId)
          if (!genericActivity) return false

          const cleaned = cleanMetadata(getActivityMetadata(genericActivity))
          updateActivity(replacementNodeId, {
            metadata: cleaned,
          })
        }
        return true
      }

      const handleCreate = (data: Record<string, unknown>): Promise<boolean> =>
        new Promise((resolve) => {
          let settled = false
          const settle = (ok: boolean) => {
            if (settled) {
              return
            }
            settled = true
            resolve(ok)
          }
          try {
            selectedNode.onSubmit(
              data,
              (newNodeId?: string) => {
                if (replacementNodeId) {
                  if (!handleReplacement(newNodeId)) {
                    showError({ title: 'Replacement failed', description: 'Failed to replace step — step not found' })
                    settle(false)
                    return
                  }
                } else if (sourceNodeId && newNodeId) {
                  moveActivityAfter(newNodeId, sourceNodeId)
                  if (onConnect) {
                    onConnect(sourceNodeId, newNodeId)
                  }
                }

                onClose()
                onNodeAdded?.()
                settle(true)
              },
              (error: string) => {
                showError({ title: 'Add step failed', description: error })
                settle(false)
              },
              nodeSubtypeId ?? undefined
            )
            // Registry onSubmit is callback-based and sync. If neither callback
            // ran, fail closed so AIAgentNodeForm does not hang waiting to markPersisted.
            if (!settled) {
              settle(false)
            }
          } catch (error) {
            showError({
              title: 'Add step failed',
              description: error instanceof Error ? error.message : 'Failed to add step',
            })
            settle(false)
          }
        })

      return (
        <FormComponent
          {...subtypeFormProps}
          initialData={initialData}
          submitButtonText={submitButtonText}
          onCancel={onClose}
          onSubmit={(data) => handleCreate(data as Record<string, unknown>)}
          onHeaderContentChange={setHeaderContent}
          projectId={projectId}
        />
      )
    }

    if (!node) return null
    return (
      <Flex key={node.id} direction={{ default: 'column' }} style={{ height: '100%', minHeight: 0 }}>
        {renderEditModeContent(node, currentWorkflow, onClose, setHeaderContent, projectId)}
      </Flex>
    )
  }

  const showInputPanel = mode === 'add' ? nodeTypeId !== RegistryNodeId.TRIGGER : node?.type !== FlowNodeType.TRIGGER
  const formId = mode === 'add' ? getAddModeFormId(nodeTypeId, nodeSubtypeId) : getEditModeFormId(node)
  const tabBarAction =
    mode === 'edit' && node?.type !== FlowNodeType.TRIGGER && !readOnly ? (
      <Button variant="secondary" onClick={onRunStep} type="button">
        Run step
      </Button>
    ) : undefined

  return (
    <NodeEditorLayout
      parametersContent={renderContent()}
      headerContent={headerContent}
      headerIcon={headerIcon}
      headerActions={headerActions}
      docLink={props.docLink}
      showInputPanel={showInputPanel}
      nodeId={node?.id}
      node={node}
      executionId={executionId}
      workflowId={workflowId}
      onClose={onClose}
      sourceNodeId={sourceNodeId}
      formId={formId}
      showNavigation={mode === 'edit'}
      onNavigateToNode={onNavigateToNode}
      onAddStep={nodeAddStepHandler}
      workflowMetadata={props.workflowMetadata}
      tabBarAction={tabBarAction}
      readOnly={readOnly}
      mode={mode}
    />
  )
}
