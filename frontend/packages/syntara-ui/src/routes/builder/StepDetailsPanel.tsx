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

import { SynStepMenu } from '../../components/steps/SynStepMenu'
import { FlowNodeType, RegistryStepId } from '../../constants'
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
import {
  StepMenuCategory,
  type StepMenuCategoryUnion,
  useStepMenuActions,
} from '../workflows/canvas/nodes/hooks/useStepMenuActions'
import type { NodeType } from '../workflows/canvas/nodes/NodeType'
import { renderStepIcon } from '../workflows/canvas/nodes/renderStepIcon'

import { StepRegistry } from './registry/StepRegistry'
import {
  ApprovalStepDetails,
  ConditionStepDetails,
  ConvergeStepDetails,
  LoopStepDetails,
  SwitchStepDetails,
  TaskStepDetails,
  TriggerStepDetails,
  WaitStepDetails,
} from './step-details'
import { StepEditorLayout } from './StepEditorLayout'
import { StepRawDataView } from './StepRawDataView'
import type { WorkflowMetadata } from './types/workflowMetadata'
import { buildPanelMenuActions } from './utils/panelMenuActions'
import { resolveIconForStep, resolveIconForType } from './utils/stepIcons'
import { getDefaultStepBaseName, getStepDisplayName } from './utils/stepNaming'

/**
 * IMPORTANT: When adding a new step type, ensure the corresponding StepDetails component
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
  return Object.keys(rest).length > 0 ? rest : undefined
}

/** Get formId for add mode based on step type and subtype */
function getAddModeFormId(
  stepTypeId: string | null | undefined,
  stepSubtypeId: string | null | undefined
): string | undefined {
  // Simple step types without subtypes
  const simpleFormMap: Record<string, string> = {
    [RegistryStepId.TRIGGER]: 'trigger-step-form',
    [RegistryStepId.ACTION]: 'action-step-form',
    [RegistryStepId.AGENT]: 'ai-agent-step-form',
    [RegistryStepId.APPROVAL]: 'approval-step-form',
  }
  if (stepTypeId && stepTypeId in simpleFormMap) return simpleFormMap[stepTypeId]

  // Logic node subtypes
  if (stepTypeId === RegistryStepId.LOGIC && stepSubtypeId) {
    const logicFormMap: Record<string, string> = {
      [RegistryStepId.LOGIC_CONDITION]: 'condition-step-form',
      [RegistryStepId.LOGIC_LOOP]: 'loop-step-form',
      [RegistryStepId.LOGIC_CONVERGE]: 'converge-step-form',
      [RegistryStepId.LOGIC_SWITCH]: 'switch-step-form',
      [RegistryStepId.LOGIC_WAIT]: 'wait-step-form',
    }
    return logicFormMap[stepSubtypeId]
  }

  // AAP Execution node subtypes
  if (stepTypeId === RegistryStepId.AAP_EXECUTION && stepSubtypeId) {
    const aapFormMap: Record<string, string> = {
      [RegistryStepId.AAP_JOB_TEMPLATE]: 'aap-job-template-form',
      [RegistryStepId.AAP_WORKFLOW_TEMPLATE]: 'aap-workflow-template-form',
    }
    return aapFormMap[stepSubtypeId]
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
    return 'ai-agent-step-form'
  }

  // Script or HTTP request
  if (executor === ExecutorTypeEnum.SCRIPT || executor === ExecutorTypeEnum.HTTP_REQUEST) {
    return 'action-step-form'
  }

  return 'action-step-form' // Default fallback
}

/** Get formId for edit mode based on step type */
function getEditModeFormId(node: Node<NodeType['data']> | undefined): string | undefined {
  if (!node) return undefined
  if (node.type === FlowNodeType.TRIGGER) return 'trigger-step-form'
  if (node.type === FlowNodeType.CONDITION) return 'condition-step-form'
  if (node.type === FlowNodeType.LOOP) return 'loop-step-form'
  if (node.type === FlowNodeType.CONVERGE) return 'converge-step-form'
  if (node.type === FlowNodeType.WAIT) return 'wait-step-form'
  if (node.type === FlowNodeType.APPROVAL) return 'approval-step-form'
  if (node.type === FlowNodeType.SWITCH) return 'switch-step-form'
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

function resolveStepMenuCategory(flowNodeType: string | undefined): StepMenuCategoryUnion {
  if (flowNodeType === FlowNodeType.TRIGGER) return StepMenuCategory.TRIGGER
  if (flowNodeType && CONTROL_FLOW_TYPES.has(flowNodeType)) return StepMenuCategory.CONTROL_FLOW
  return StepMenuCategory.ACTIVITY
}

function getNodeDisabledState(node: Node<NodeType['data']> | undefined): boolean {
  if (!node?.data) return false
  const nodeSettings = Reflect.get(node.data, 'settings') as { disabled?: boolean } | undefined
  return nodeSettings?.disabled ?? false
}

/** Top-level search is correct: the builder store always holds a flat activity list (see WorkflowTransform). */
function findActivityInCurrentWorkflow(activityId: string): Activity | undefined {
  const current = useWorkflowStore.getState().currentWorkflow
  return current?.workflow.activities.find((activity: Activity) => activity.id === activityId)
}

/** Renders the appropriate details component for a given node in edit mode. */
function renderEditModeContent(params: {
  node: Node<NodeType['data']>
  currentWorkflow: ReturnType<typeof selectCurrentWorkflow>
  onClose: () => void
  onHeaderContentChange: (content: ReactNode | null) => void
  projectId?: string
}): ReactNode {
  const { node, currentWorkflow, onClose, onHeaderContentChange, projectId } = params
  if (node.type === FlowNodeType.TRIGGER) {
    const triggerIdx = parseTriggerIndex(node.id) ?? 0
    const trigger = currentWorkflow?.triggers?.[triggerIdx]
    if (trigger) {
      return (
        <TriggerStepDetails
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
      <TaskStepDetails
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
      <ApprovalStepDetails
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
      <ConditionStepDetails
        conditionData={node.data as ConditionActivity}
        nodeId={node.id}
        onClose={onClose}
        onHeaderContentChange={onHeaderContentChange}
      />
    )
  }

  if (node.type === FlowNodeType.LOOP) {
    return (
      <LoopStepDetails
        loopData={node.data as LoopActivity}
        nodeId={node.id}
        onClose={onClose}
        onHeaderContentChange={onHeaderContentChange}
      />
    )
  }

  if (node.type === FlowNodeType.CONVERGE) {
    return (
      <ConvergeStepDetails
        convergeData={node.data as ConvergeActivity}
        nodeId={node.id}
        onClose={onClose}
        onHeaderContentChange={onHeaderContentChange}
      />
    )
  }

  if (node.type === FlowNodeType.SWITCH) {
    return (
      <SwitchStepDetails
        switchData={node.data as SwitchActivity}
        nodeId={node.id}
        onClose={onClose}
        onHeaderContentChange={onHeaderContentChange}
      />
    )
  }

  if (node.type === FlowNodeType.WAIT) {
    return (
      <WaitStepDetails
        waitData={node.data as WaitActivity}
        nodeId={node.id}
        onClose={onClose}
        onHeaderContentChange={onHeaderContentChange}
      />
    )
  }

  return <StepRawDataView node={node} />
}

type StepDetailsPanelProps = {
  mode: 'add' | 'edit'
  node?: Node<NodeType['data']>
  stepTypeId?: string | null
  stepSubtypeId?: string | null
  sourceNodeId?: string | null
  replacementNodeId?: string | null
  executionId?: string | null
  workflowId?: string | null
  onConnect?: (sourceId: string, targetId: string) => void
  onClose: () => void
  projectId?: string
  onNavigateToStep?: (nodeId: string) => void
  onAddStep?: (sourceNodeId: string, sourceHandle?: string) => void
  docLink?: string
  workflowMetadata?: WorkflowMetadata
  onRunStep?: () => void
  readOnly?: boolean
  onStepAdded?: () => void
}

function createAddStepHandler(
  nodeId: string | undefined,
  onAddStep: ((sourceNodeId: string, sourceHandle?: string) => void) | undefined
): ((handle?: string) => void) | undefined {
  if (!nodeId || !onAddStep) return undefined
  return (handle?: string) => onAddStep(nodeId, handle)
}

export function StepDetailsPanel(props: StepDetailsPanelProps) {
  const {
    mode,
    node,
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
    onRunStep,
    readOnly,
    onStepAdded,
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
  const stepMenuCategory = resolveStepMenuCategory(node?.type)
  const nodeAddStepHandler = createAddStepHandler(nodeId, onAddStep)
  const menuActions = useStepMenuActions({
    nodeId: nodeId ?? 'unknown',
    stepCategory: stepMenuCategory,
    triggerIndex: isTriggerNode ? triggerIndex : undefined,
    disabled: getNodeDisabledState(node),
  })
  const panelMenuActions = buildPanelMenuActions(mode, node, menuActions, onClose)
  const headerActions = panelMenuActions.length > 0 ? <SynStepMenu menuActions={panelMenuActions} /> : null

  const iconDescriptor =
    mode === 'edit' && node
      ? resolveIconForStep(node, currentWorkflow)
      : resolveIconForType({ stepTypeId, stepSubtypeId })
  const headerIcon = renderStepIcon(iconDescriptor.icon, iconDescriptor.id, 'header')

  const renderContent = () => {
    if (mode === 'add') {
      const selectedNode = stepTypeId ? StepRegistry.get(stepTypeId) : null
      const selectedSubtype = selectedNode?.subtypes?.find((subtype) => subtype.id === stepSubtypeId) ?? null

      if (!selectedNode) return null

      const initialData = {
        ...(selectedSubtype?.initialData ?? {}),
      } as Record<string, unknown>

      initialData.name ??= getStepDisplayName(
        getDefaultStepBaseName({
          stepTypeId: selectedNode.id,
          stepSubtypeId: selectedSubtype?.id,
          initialData,
          label: selectedSubtype?.label ?? selectedNode.label,
        })
      )

      // For nodes with subtypes, use the subtype's form component
      const FormComponent = selectedSubtype?.formComponent ?? selectedNode.formComponent
      const subtypeFormProps = selectedSubtype?.formProps ?? {}
      const submitButtonText = 'Add step'

      /** Returns true if replacement succeeded, false if lookup failed. */
      const handleReplacement = (newStepId: string | undefined): boolean => {
        if (!replacementNodeId) return false

        if (newStepId) {
          const newActivity = findActivityInCurrentWorkflow(newStepId)
          if (!newActivity) return false

          removeActivity(newStepId)
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
              (newStepId?: string) => {
                if (replacementNodeId) {
                  if (!handleReplacement(newStepId)) {
                    showError({ title: 'Replacement failed', description: 'Failed to replace step — step not found' })
                    settle(false)
                    return
                  }
                } else if (sourceNodeId && newStepId) {
                  moveActivityAfter(newStepId, sourceNodeId)
                  if (onConnect) {
                    onConnect(sourceNodeId, newStepId)
                  }
                }

                onClose()
                onStepAdded?.()
                settle(true)
              },
              (error: string) => {
                showError({ title: 'Add step failed', description: error })
                settle(false)
              },
              stepSubtypeId ?? undefined
            )
            // Registry onSubmit is callback-based and sync. If neither callback
            // ran, fail closed so AIAgentStepForm does not hang waiting to markPersisted.
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
        {renderEditModeContent({
          node,
          currentWorkflow,
          onClose,
          onHeaderContentChange: setHeaderContent,
          projectId,
        })}
      </Flex>
    )
  }

  const showInputPanel = mode === 'add' ? stepTypeId !== RegistryStepId.TRIGGER : node?.type !== FlowNodeType.TRIGGER
  const formId = mode === 'add' ? getAddModeFormId(stepTypeId, stepSubtypeId) : getEditModeFormId(node)
  const tabBarAction =
    mode === 'edit' && node?.type !== FlowNodeType.TRIGGER && !readOnly ? (
      <Button variant="secondary" onClick={onRunStep} type="button">
        Run step
      </Button>
    ) : undefined

  return (
    <StepEditorLayout
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
      onNavigateToStep={onNavigateToStep}
      onAddStep={nodeAddStepHandler}
      workflowMetadata={props.workflowMetadata}
      tabBarAction={tabBarAction}
      readOnly={readOnly}
      mode={mode}
    />
  )
}
