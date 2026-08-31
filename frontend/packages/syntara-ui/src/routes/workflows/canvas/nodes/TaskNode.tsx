import { ExecutorTypeEnum, type TaskActivity } from '@syntara/contracts'
import { type Node, type NodeProps } from '@xyflow/react'

import { SynDetailList } from '../../../../components/details/SynDetailList'
import { FlowNodeType } from '../../../../constants'
import type { ActivityStatus } from '../../execution/types'
import { getNodeTypeColor } from '../nodeTypeColors'

import { renderCondition, renderJson, renderText } from './common/detailRenderers'
import { detectTaskNodeType, type TaskActivityWithMetadata } from './common/detectTaskNodeType'
import { NodeBody } from './common/NodeBody'
import { NodeComponent } from './common/NodeComponent'
import { StandardNodeHeader } from './common/StandardNodeHeader'
import { useCredentialName } from './hooks/useCredentialName'
import { MenuNodeType, useNodeMenuActions } from './hooks/useNodeMenuActions'
import { getTaskIconDescriptor } from './nodeIconResolver'
import { nodeMetadata, executorMetadata } from './nodeMetadata'
import { renderNodeIcon } from './renderNodeIcon'
import { getTaskSemanticLabels } from './taskSemanticLabels'

type AAPJobTemplateConfig = {
  job_template_id?: number
  job_template_name?: string
  inventory_id?: number
  inventory_name?: string
}

type AAPWorkflowTemplateConfig = {
  workflow_job_template_name?: string
  inventory_name?: string
}

/** Parameters for an agentic (Task Agent) node on the canvas. */
type AgenticConfig = {
  /** UUIDs of selected tools when strategy is SELECTED. */
  tool_selections?: string[]
  /** Tool availability: ALL, NONE, or SELECTED. */
  tool_selection_strategy?: string
  /** UUID of the LLM provider credential. */
  credential_id?: string
  /** LLM model identifier (e.g. "anthropic/claude-haiku-4.5"). */
  model?: string
  /** Attached context file UUIDs. */
  file_ids?: string[]
}

function AgenticNodeDetails({ config, toolsText }: { config: AgenticConfig; toolsText?: string }) {
  const { name: credentialName } = useCredentialName(config.credential_id)
  const fileCount = config.file_ids?.length ?? 0
  return (
    <>
      {renderText('Model', config.model)}
      {renderText('Credential', credentialName)}
      {renderText('Tools', toolsText)}
      {fileCount > 0 && renderText('Files', `${fileCount} attached`)}
    </>
  )
}

export type TaskNode = { type: typeof FlowNodeType.TASK } & Node<TaskActivity>

export function TaskNodeComponent(props: NodeProps<TaskNode>) {
  const metadata = nodeMetadata.task
  const menuActions = useNodeMenuActions({
    nodeId: props.data.id,
    nodeType: MenuNodeType.ACTIVITY,
    disabled: props.data.settings?.disabled ?? false,
  })

  // Extract execution state if present
  const executionState = (props.data as Record<string, unknown>).__executionState as
    | {
        status: ActivityStatus
        started_at?: string
        completed_at?: string
        error_details?: string
        retry_count?: number
      }
    | undefined

  const showExecutionBadge =
    (props.data as { metadata?: { __showExecutionBadge?: boolean } }).metadata?.__showExecutionBadge === true

  return (
    <NodeComponent
      className={metadata.className}
      nodeProps={props}
      executionState={executionState}
      showExecutionBadge={showExecutionBadge}
      topBarColor={getNodeTypeColor(FlowNodeType.TASK, props.data)}
      semanticZoomSummary={getTaskSemanticLabels(props.data)}
    >
      <TaskActivityDetails
        data={props.data}
        menuActions={menuActions}
        iconColor={getNodeTypeColor(FlowNodeType.TASK, props.data)}
      />
    </NodeComponent>
  )
}

// eslint-disable-next-line complexity
export function TaskActivityDetails(
  props: Readonly<{
    data: TaskActivity
    showJson?: boolean
    menuActions?: ReturnType<typeof useNodeMenuActions>
    /** Optional color so icon matches node type accent (same as top bar) */
    iconColor?: string
  }>
) {
  // Detect the actual node type — in v2, activity.type IS the executor
  const { actualExecutor } = detectTaskNodeType(props.data)
  const dataWithMetadata = props.data as TaskActivityWithMetadata

  const executorMeta = executorMetadata[actualExecutor] ?? executorMetadata[props.data.type ?? '']
  const { id: iconId } = getTaskIconDescriptor(props.data)
  const iconNode = renderNodeIcon(executorMeta?.icon, iconId, 'canvas', props.iconColor)
  const taskExecutorLabel = executorMeta?.label ?? 'Task'
  const taskExecutor = actualExecutor || (props.data.type ?? '')
  const config = props.data.parameters ?? {}
  const isAapJobTemplate = taskExecutor === ExecutorTypeEnum.AAP_JOB_TEMPLATE
  const isAapWorkflowTemplate = taskExecutor === ExecutorTypeEnum.AAP_WORKFLOW_JOB_TEMPLATE
  const aapJobConfig = isAapJobTemplate ? (config as AAPJobTemplateConfig) : null
  const aapWorkflowConfig = isAapWorkflowTemplate ? (config as AAPWorkflowTemplateConfig) : null
  const agentConfig = taskExecutor === ExecutorTypeEnum.AGENTIC ? (config as AgenticConfig) : undefined

  const formatCount = (count: number, singular: string, plural = `${singular}s`) =>
    `${count} ${count === 1 ? singular : plural}`

  const toolsCount = agentConfig?.tool_selections?.length
  const toolsText = toolsCount !== undefined ? formatCount(toolsCount, 'tool') : undefined

  // Helper to detect if a value is an expression (${...} or {{...}})
  const isExpression = (value?: string): boolean => {
    if (!value) return false
    const trimmed = value.trim()
    return trimmed.includes('${') || trimmed.includes('{{')
  }

  return (
    <>
      <StandardNodeHeader
        icon={iconNode}
        badge={undefined}
        title={props.data.name}
        subtitle={taskExecutorLabel}
        expandable
        menuActions={props.menuActions}
      />
      <NodeBody>
        <SynDetailList>
          {renderCondition(dataWithMetadata.condition)}
          {taskExecutor === ExecutorTypeEnum.SCRIPT && (
            <>{renderText('Language', (config as { language: string }).language)}</>
          )}
          {taskExecutor === ExecutorTypeEnum.HTTP_REQUEST && (
            <>
              {renderText('Method', (config as { method: string }).method)}
              {renderText('URL', (config as { url: string }).url)}
            </>
          )}
          {renderText(
            isExpression(aapJobConfig?.job_template_name) ? 'Job template expression' : 'Job template',
            aapJobConfig?.job_template_name
          )}
          {renderText(
            isExpression(aapWorkflowConfig?.workflow_job_template_name)
              ? 'Workflow job template expression'
              : 'Workflow job template',
            aapWorkflowConfig?.workflow_job_template_name
          )}
          {taskExecutor === ExecutorTypeEnum.AGENTIC && (
            <AgenticNodeDetails config={config as AgenticConfig} toolsText={toolsText} />
          )}
          {taskExecutor !== ExecutorTypeEnum.SCRIPT && renderJson(props.data, props.showJson)}
        </SynDetailList>
      </NodeBody>
    </>
  )
}
