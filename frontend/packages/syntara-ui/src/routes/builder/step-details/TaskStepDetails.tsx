import {
  ActivityTypeEnum,
  ExecutorTypeEnum,
  type Activity,
  type NodeSettings,
  type TaskActivity,
} from '@syntara/contracts'
import type { ReactNode } from 'react'

import { useAlerts, type AlertMessage } from '../../../providers/alerts'
import {
  detectTaskExecutorType,
  DetectedExecutorType,
} from '../../../routes/workflows/canvas/nodes/common/detectTaskExecutorType'
import {
  createAAPJobTemplateActivity,
  createAAPWorkflowTemplateActivity,
  useWorkflowStoreActions,
} from '../../../stores/useWorkflowStore'
import type { AAPJobTemplateConfig } from '../../../stores/workflowFactories'
import { AAPJobTemplateForm } from '../step-forms/AAPJobTemplateForm'
import type { AAPJobTemplateFormData } from '../step-forms/aapJobTemplateSchema'
import { AAPWorkflowTemplateForm } from '../step-forms/AAPWorkflowTemplateForm'
import type { AAPWorkflowTemplateFormData } from '../step-forms/aapWorkflowTemplateSchema'
import { ActionStepForm } from '../step-forms/ActionStepForm'
import type { ActionFormData as RegistryActionFormData } from '../stepFormTypes'
import {
  buildAAPConfig,
  buildAAPWorkflowTemplateConfig,
  buildExpressionModeActivity,
  buildWorkflowExpressionModeActivity,
  isJobTemplateInputVariablesMode,
  isWorkflowTemplateInputVariablesMode,
  resolveJobTemplateUseInputVariables,
  resolveWorkflowUseInputVariables,
  validateJobTemplateId,
  validateWorkflowTemplateId,
} from '../utils/aapHelpers'

import { AIAgentStepDetails } from './AIAgentStepDetails'
import { buildRegistryActionInitialData, buildRegistryActivityUpdate } from './taskStepSubmitHelpers'

/**
 * Stored AAP config supports both snake_case (API) and camelCase (legacy) field names.
 * Extends AAPJobTemplateConfig with snake_case API fields for backend compatibility.
 */
type StoredAAPConfig = AAPJobTemplateConfig & {
  // Snake_case API field names (backend format)
  credential_id?: string
  integration_id?: string
  organization_id?: number
  organization_name?: string
  job_template_id?: number
  job_template_name?: string
  inventory_id?: number
  inventory_name?: string
  extra_vars?: Record<string, unknown>
  skip_tags?: string
  job_type?: string
  job_slice_count?: number
  diff_mode?: boolean
  execution_environment?: string
  instance_group?: string
  instance_group_name?: string
  instance_group_id?: number
  job_credentials?: number[]

  // Index signature for unknown fields
  [key: string]: unknown
}

/** Stringify extra vars object or return empty string. */
function serializeExtraVars(extraVars: Record<string, unknown> | undefined): string {
  return extraVars ? JSON.stringify(extraVars, null, 2) : ''
}

/** Get field value with snake_case → camelCase fallback. */
function getField<T>(snakeCase: T | undefined, camelCase: T | undefined, defaultValue: T): T {
  return snakeCase ?? camelCase ?? defaultValue
}

/**
 * Type guard to check if config has AAP job template fields.
 * Checks both normal mode (job_template_id) and expression mode (job_template_name).
 */
function hasJobTemplateConfig(config: Record<string, unknown>): config is StoredAAPConfig {
  return (
    'job_template_id' in config ||
    'jobTemplateId' in config ||
    'job_template_name' in config ||
    'jobTemplateName' in config ||
    'use_input_variables' in config ||
    'useInputVariables' in config ||
    'extra_vars' in config ||
    'extraVars' in config
  )
}

/**
 * Build initial form data from a stored AAP job template config.
 * Handles both snake_case (API) and camelCase (legacy) field names.
 */
function getStringField(config: Record<string, unknown>, ...keys: string[]): string | undefined {
  for (const key of keys) {
    const val = config[key]
    if (typeof val === 'string') return val
  }
  return undefined
}

function buildAAPInitialData(taskName: string, config: Record<string, unknown>): Partial<AAPJobTemplateFormData> {
  if (!hasJobTemplateConfig(config)) {
    return { name: taskName }
  }
  const c = config
  const organizationName = getField(c.organization_name, c.organization, '')
  const jobTemplateName = getField(c.job_template_name, c.jobTemplateName, '')
  const inventoryName = getField(c.inventory_name, c.inventoryName, '')
  const extraVars = serializeExtraVars(c.extra_vars ?? c.extraVars)

  return {
    name: taskName,
    credential_id: getStringField(c, 'credential_id', 'credentialId'),
    integration_id: getStringField(c, 'integration_id', 'integrationId'),
    organization_id: c.organization_id ?? c.organizationId,
    organization_name: organizationName,
    job_template_name: jobTemplateName,
    job_template_id: (c.job_template_id ?? c.jobTemplateId) as number | undefined,
    inventory_name: inventoryName,
    inventory_id: c.inventory_id ?? c.inventory,
    extra_vars: extraVars,
    limit: c.limit ?? '',
    tags: c.tags ?? '',
    skip_tags: c.skip_tags ?? c.skipTags ?? '',
    verbosity: c.verbosity?.toString() ?? '',
    job_credentials: c.jobCredentials ?? c.job_credentials ?? [],
    job_type: getField(c.job_type, c.jobType, ''),
    forks: c.forks,
    job_slice_count: c.job_slice_count ?? c.jobSlicing,
    diff_mode: getField(c.diff_mode, c.diffMode, false),
    execution_environment: getField(c.execution_environment, c.executionEnvironment, ''),
    instance_group: getField(c.instance_group_name, c.instanceGroupName, ''),
    instance_group_id: c.instance_group_id ?? c.instanceGroupId,
    labels: c.labels ?? [],
    use_input_variables: resolveJobTemplateUseInputVariables(c),
  }
}

/**
 * Build initial form data from a stored AAP workflow template config.
 */
function buildAAPWorkflowInitialData(
  taskName: string,
  config: Record<string, unknown>
): Partial<AAPWorkflowTemplateFormData> {
  const c = config
  const organizationName = getField(c.organization_name, c.organization, '') as string
  const workflowTemplateName = getField(c.workflow_job_template_name, c.workflowJobTemplateName, '') as string
  const inventoryName = getField(c.inventory_name, c.inventoryName, '') as string
  const extraVars = serializeExtraVars((c.extra_vars ?? c.extraVars) as Record<string, unknown> | undefined)

  return {
    name: taskName,
    credential_id: getStringField(c, 'credential_id', 'credentialId'),
    integration_id: getStringField(c, 'integration_id', 'integrationId'),
    organization_id: (c.organization_id ?? c.organizationId) as number | undefined,
    organization_name: organizationName,
    workflow_job_template_name: workflowTemplateName,
    workflow_job_template_id: (c.workflow_job_template_id ?? c.workflowJobTemplateId) as number | undefined,
    inventory_name: inventoryName,
    inventory_id: (c.inventory_id ?? c.inventory) as number | undefined,
    extra_vars: extraVars,
    limit: (c.limit ?? '') as string,
    scm_branch: (c.scm_branch ?? c.scmBranch ?? '') as string,
    tags: (c.tags ?? '') as string,
    skip_tags: (c.skip_tags ?? c.skipTags ?? '') as string,
    labels: (c.labels ?? []) as string[],
    use_input_variables: resolveWorkflowUseInputVariables(c, {
      organizationName,
      workflowTemplateName,
      inventoryName,
      limit: (c.limit ?? '') as string,
      scmBranch: (c.scm_branch ?? c.scmBranch ?? '') as string,
      tags: (c.tags ?? '') as string,
      skipTags: (c.skip_tags ?? c.skipTags ?? '') as string,
      extraVars,
    }),
  }
}

type TaskStepDetailsProps = {
  readonly taskData: Activity
  readonly nodeId: string
  readonly onClose: () => void
  readonly onHeaderContentChange: (content: ReactNode | null) => void
  readonly projectId?: string
}

type AAPTaskProps = {
  readonly actualExecutor: string
  readonly config: Record<string, unknown>
  readonly taskName: string
  readonly nodeId: string
  readonly settings: NodeSettings | undefined
  readonly onClose: () => void
  readonly onHeaderContentChange: (content: ReactNode | null) => void
  readonly projectId?: string
  readonly showError: (alert: AlertMessage) => void
  readonly updateActivity: (id: string, activity: Partial<Activity>) => void
}

/**
 * Render AAP task details (job template or workflow template).
 * Extracted to reduce cognitive complexity of TaskStepDetails.
 */
function renderAAPTaskDetails({
  actualExecutor,
  config,
  taskName,
  nodeId,
  settings,
  onClose,
  onHeaderContentChange,
  projectId,
  showError,
  updateActivity,
}: AAPTaskProps) {
  // Branch based on actual executor type
  if (actualExecutor === ExecutorTypeEnum.AAP_WORKFLOW_JOB_TEMPLATE) {
    const workflowInitialData = { ...buildAAPWorkflowInitialData(taskName, config), settings }

    const handleWorkflowSubmit = (data: AAPWorkflowTemplateFormData) => {
      try {
        if (isWorkflowTemplateInputVariablesMode(data)) {
          updateActivity(nodeId, buildWorkflowExpressionModeActivity(nodeId, data.name, data))
        } else {
          const workflow_job_template_id = validateWorkflowTemplateId(data.workflow_job_template_id)
          const workflowConfig = buildAAPWorkflowTemplateConfig(data)
          updateActivity(
            nodeId,
            createAAPWorkflowTemplateActivity({
              id: nodeId,
              name: data.name,
              workflowTemplateId: workflow_job_template_id,
              config: workflowConfig,
              settings: data.settings,
            })
          )
        }

        onClose()
      } catch (error) {
        showError({
          title: 'Update failed',
          description: error instanceof Error ? error.message : 'Failed to update step',
        })
      }
    }

    return (
      <AAPWorkflowTemplateForm
        initialData={workflowInitialData}
        onSubmit={handleWorkflowSubmit}
        onCancel={onClose}
        onHeaderContentChange={onHeaderContentChange}
        projectId={projectId}
      />
    )
  }

  // Default to AAP job template
  const aapInitialData = { ...buildAAPInitialData(taskName, config), settings }

  const handleAAPSubmit = (data: AAPJobTemplateFormData) => {
    try {
      if (isJobTemplateInputVariablesMode(data)) {
        updateActivity(nodeId, buildExpressionModeActivity(nodeId, data.name, data))
      } else {
        const job_template_id = validateJobTemplateId(data.job_template_id)
        const aapStepConfig = buildAAPConfig(data)
        updateActivity(
          nodeId,
          createAAPJobTemplateActivity({
            id: nodeId,
            name: data.name,
            jobTemplateId: job_template_id,
            config: aapStepConfig,
            settings: data.settings,
          })
        )
      }

      onClose()
    } catch (error) {
      showError({
        title: 'Update failed',
        description: error instanceof Error ? error.message : 'Failed to update step',
      })
    }
  }

  return (
    <AAPJobTemplateForm
      initialData={aapInitialData}
      onSubmit={handleAAPSubmit}
      onCancel={onClose}
      onHeaderContentChange={onHeaderContentChange}
      projectId={projectId}
    />
  )
}

export function TaskStepDetails({
  taskData,
  nodeId,
  onClose,
  onHeaderContentChange,
  projectId,
}: Readonly<TaskStepDetailsProps>) {
  const { showError } = useAlerts()
  // Use action accessor - component won't re-render when store state changes
  const { updateActivity } = useWorkflowStoreActions()

  // Don't show action form for approval nodes - they have their own form
  if (taskData.type === ActivityTypeEnum.APPROVAL) {
    return null
  }

  // In v2, activity.type IS the executor directly
  const executor = taskData.type

  // Detect the executor type, including AAP and connector tasks.
  const { actualExecutor, detectedExecutorType } = detectTaskExecutorType(taskData as TaskActivity)

  // In v2, parameters are at activity.parameters (not activity.task.parameters)
  const config = taskData.parameters ?? {}

  // AAP (incl. connector-backed with executor still "agentic") must be checked before the generic
  // agentic branch, or those tasks would incorrectly show AI Agent details.
  const isAAPTask =
    detectedExecutorType === DetectedExecutorType.AAP ||
    actualExecutor === ExecutorTypeEnum.AAP_JOB_TEMPLATE ||
    actualExecutor === ExecutorTypeEnum.AAP_WORKFLOW_JOB_TEMPLATE
  if (isAAPTask) {
    return renderAAPTaskDetails({
      actualExecutor,
      config,
      taskName: taskData.name ?? '',
      nodeId,
      settings: taskData.settings,
      onClose,
      onHeaderContentChange,
      projectId,
      showError,
      updateActivity,
    })
  }

  // True agentic tasks (not AAP-in-disguise)
  if (executor === ExecutorTypeEnum.AGENTIC) {
    return (
      <AIAgentStepDetails
        taskData={taskData}
        nodeId={nodeId}
        onClose={onClose}
        onHeaderContentChange={onHeaderContentChange}
        projectId={projectId}
      />
    )
  }

  // Handle standard executors (script, http_request)
  if (executor !== ExecutorTypeEnum.SCRIPT && executor !== ExecutorTypeEnum.HTTP_REQUEST) {
    return null
  }

  const taskActivity = taskData as TaskActivity
  const initialData = buildRegistryActionInitialData(executor, config, taskActivity)

  const handleSubmit = (data: RegistryActionFormData) => {
    try {
      updateActivity(nodeId, buildRegistryActivityUpdate(taskActivity, data))
      onClose()
    } catch (error) {
      showError({
        title: 'Update failed',
        description: error instanceof Error ? error.message : 'Failed to update step',
      })
    }
  }

  return (
    <ActionStepForm
      initialData={initialData}
      onSubmit={handleSubmit}
      onHeaderContentChange={onHeaderContentChange}
      projectId={projectId}
    />
  )
}
