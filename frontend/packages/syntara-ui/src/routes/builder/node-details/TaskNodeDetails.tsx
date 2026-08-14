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
  detectTaskNodeType,
  DetectedExecutorType,
} from '../../../routes/workflows/canvas/nodes/common/detectTaskNodeType'
import {
  createAAPJobTemplateActivity,
  createAAPWorkflowTemplateActivity,
  useWorkflowStoreActions,
} from '../../../stores/useWorkflowStore'
import type { AAPJobTemplateConfig } from '../../../stores/workflowFactories'
import { generateUUID } from '../../../utils/generateUUID'
import { PROTOTYPE_POLLUTION_KEYS } from '../../../utils/jsonSafeParse'
import { parseJsonEnvironment } from '../../../utils/parseJsonEnvironment'
import type { ActionFormData as RegistryActionFormData } from '../hooks/useNodeCreation'
import { AAPJobTemplateForm } from '../node-forms/AAPJobTemplateForm'
import type { AAPJobTemplateFormData } from '../node-forms/aapJobTemplateSchema'
import { AAPWorkflowTemplateForm } from '../node-forms/AAPWorkflowTemplateForm'
import type { AAPWorkflowTemplateFormData } from '../node-forms/aapWorkflowTemplateSchema'
import { ActionNodeForm } from '../node-forms/ActionNodeForm'
import {
  buildAAPConfig,
  buildAAPWorkflowTemplateConfig,
  buildExpressionModeActivity,
  buildWorkflowExpressionModeActivity,
  hasExpressionValue,
  validateJobTemplateId,
  validateWorkflowTemplateId,
} from '../utils/aapHelpers'

import { AIAgentNodeDetails } from './AIAgentNodeDetails'

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

/**
 * SECURITY: JSON.parse reviver that strips prototype pollution keys during parsing.
 */
function safeJSONReviver(key: string, value: unknown): unknown {
  if (key === '__proto__' || key === 'constructor' || key === 'prototype') {
    return undefined
  }
  return value
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
    'jobTemplateName' in config
  )
}

/**
 * Convert key-value entries from the form into a flat headers object.
 * Skips entries with empty keys and prototype pollution keys.
 */
function parseHeaders(entries: Array<{ key: string; value: string }> | undefined): Record<string, string> | undefined {
  if (!entries?.length) return undefined

  const result: Record<string, string> = {}
  for (const { key, value } of entries) {
    const trimmedKey = key.trim()
    if (trimmedKey && !PROTOTYPE_POLLUTION_KEYS.has(trimmedKey)) result[trimmedKey] = value
  }
  return Object.keys(result).length > 0 ? result : undefined
}

/**
 * Build activity config and validate form data for submission.
 */
function buildActivityConfig(
  data: RegistryActionFormData
):
  | { language: string; code: string; credential_id?: string }
  | { method: string; url: string; headers?: Record<string, string>; body?: unknown; credential_id?: string } {
  const isScript = data.executor === ExecutorTypeEnum.SCRIPT

  if (isScript) {
    return buildScriptConfig(data)
  }

  const parsedHeaders = parseHeaders(data.headers)
  return buildHTTPConfig(data, parsedHeaders)
}

/**
 * Build HTTP request config from form data.
 */
function buildHTTPConfig(
  data: RegistryActionFormData,
  headers: Record<string, string> | undefined
): { method: string; url: string; headers?: Record<string, string>; body?: unknown; credential_id?: string } {
  const parsedBody = data.body
    ? (() => {
        try {
          return JSON.parse(data.body, safeJSONReviver) as unknown
        } catch {
          return data.body as unknown
        }
      })()
    : undefined

  const config: {
    method: string
    url: string
    headers?: Record<string, string>
    body?: unknown
    credential_id?: string
  } = {
    method: data.method as 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE',
    url: data.url!,
  }

  if (headers) {
    config.headers = headers
  }
  if (parsedBody !== undefined) {
    config.body = parsedBody
  }
  if (data.credential_id) {
    config.credential_id = data.credential_id
  }

  return config
}

/**
 * Serialize body config for HTTP request.
 */
function serializeBody(body: unknown): string {
  if (typeof body === 'string') return body
  return JSON.stringify(body, null, 2)
}

/**
 * Build script config from form data.
 */
function buildScriptConfig(data: RegistryActionFormData): {
  language: string
  code: string
  credential_id?: string
  environment?: Record<string, string>
} {
  const config: { language: string; code: string; credential_id?: string; environment?: Record<string, string> } = {
    language: data.language ?? 'python',
    code: data.code!,
  }

  if (data.credential_id) {
    config.credential_id = data.credential_id
  }

  const env = parseJsonEnvironment(data.parameters)
  if (env) {
    config.environment = env
  }

  return config
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

  return {
    name: taskName,
    credential_id: getStringField(c, 'credential_id', 'credentialId'),
    integration_id: getStringField(c, 'integration_id', 'integrationId'),
    organization_id: c.organization_id ?? c.organizationId,
    organization_name: getField(c.organization_name, c.organization, ''),
    job_template_name: getField(c.job_template_name, c.jobTemplateName, ''),
    job_template_id: (c.job_template_id ?? c.jobTemplateId) as number | undefined,
    inventory_name: getField(c.inventory_name, c.inventoryName, ''),
    inventory_id: c.inventory_id ?? c.inventory,
    extra_vars: serializeExtraVars(c.extra_vars ?? c.extraVars),
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
    instance_group: getField(c.instance_group_name, c.instanceGroupName, '') as string | undefined,
    instance_group_id: c.instance_group_id ?? c.instanceGroupId,
    labels: c.labels ?? [],
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
  return {
    name: taskName,
    credential_id: getStringField(c, 'credential_id', 'credentialId'),
    integration_id: getStringField(c, 'integration_id', 'integrationId'),
    organization_id: (c.organization_id ?? c.organizationId) as number | undefined,
    organization_name: getField(c.organization_name, c.organization, '') as string | undefined,
    workflow_job_template_name: getField(c.workflow_job_template_name, c.workflowJobTemplateName, '') as
      | string
      | undefined,
    workflow_job_template_id: (c.workflow_job_template_id ?? c.workflowJobTemplateId) as number | undefined,
    inventory_name: getField(c.inventory_name, c.inventoryName, '') as string | undefined,
    inventory_id: (c.inventory_id ?? c.inventory) as number | undefined,
    extra_vars: serializeExtraVars((c.extra_vars ?? c.extraVars) as Record<string, unknown> | undefined),
    limit: (c.limit ?? '') as string,
    scm_branch: (c.scm_branch ?? c.scmBranch ?? '') as string,
    tags: (c.tags ?? '') as string,
    skip_tags: (c.skip_tags ?? c.skipTags ?? '') as string,
    labels: (c.labels ?? []) as string[],
  }
}

type TaskNodeDetailsProps = {
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
 * Extracted to reduce cognitive complexity of TaskNodeDetails.
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
        if (hasExpressionValue(data.workflow_job_template_name, data.organization_name)) {
          updateActivity(nodeId, buildWorkflowExpressionModeActivity(nodeId, data.name, data))
        } else {
          const workflow_job_template_id = validateWorkflowTemplateId(data.workflow_job_template_id)
          const workflowConfig = buildAAPWorkflowTemplateConfig(data)
          updateActivity(
            nodeId,
            createAAPWorkflowTemplateActivity(
              nodeId,
              data.name,
              workflow_job_template_id,
              workflowConfig,
              data.settings
            )
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
      if (hasExpressionValue(data.job_template_name, data.organization_name)) {
        updateActivity(nodeId, buildExpressionModeActivity(nodeId, data.name, data))
      } else {
        const job_template_id = validateJobTemplateId(data.job_template_id)
        const aapNodeConfig = buildAAPConfig(data)
        updateActivity(
          nodeId,
          createAAPJobTemplateActivity(nodeId, data.name, job_template_id, aapNodeConfig, data.settings)
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

function buildExecutorInitialData(
  executor: string,
  config: Record<string, unknown>,
  taskData: Activity
): Partial<RegistryActionFormData> {
  const isScript = executor === ExecutorTypeEnum.SCRIPT
  const isHTTP = executor === ExecutorTypeEnum.HTTP_REQUEST
  const serializedBody = isHTTP && config.body ? serializeBody(config.body) : undefined

  return {
    name: taskData.name,
    executor: isScript ? ExecutorTypeEnum.SCRIPT : ExecutorTypeEnum.HTTP_REQUEST,
    language: isScript ? (config.language as string | undefined) : undefined,
    code: isScript ? (config.code as string | undefined) : undefined,
    parameters: isScript && config.environment ? JSON.stringify(config.environment, null, 2) : undefined,
    method: isHTTP ? (config.method as 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE' | undefined) : undefined,
    url: isHTTP ? (config.url as string | undefined) : undefined,
    headers:
      isHTTP && config.headers
        ? Object.entries(config.headers as Record<string, string>).map(([key, value]) => ({
            id: generateUUID(),
            key,
            value: String(value),
          }))
        : undefined,
    body: serializedBody,
    credential_id:
      (config as { credentialId?: string; credential_id?: string }).credentialId ??
      (config as { credentialId?: string; credential_id?: string }).credential_id ??
      undefined,
    settings: taskData.settings,
  }
}

export function TaskNodeDetails({
  taskData,
  nodeId,
  onClose,
  onHeaderContentChange,
  projectId,
}: Readonly<TaskNodeDetailsProps>) {
  const { showError } = useAlerts()
  // Use action accessor - component won't re-render when store state changes
  const { updateActivity } = useWorkflowStoreActions()

  // Don't show action form for approval nodes - they have their own form
  if (taskData.type === ActivityTypeEnum.APPROVAL) {
    return null
  }

  // In v2, activity.type IS the executor directly
  const executor = taskData.type

  // Detect the actual node type - handles disguised AAP/connector nodes
  const { actualExecutor, detectedExecutorType } = detectTaskNodeType(taskData as TaskActivity)

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
      <AIAgentNodeDetails
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

  const initialData = buildExecutorInitialData(executor, config, taskData)

  const handleSubmit = (data: RegistryActionFormData) => {
    try {
      const config = buildActivityConfig(data)

      const updatedActivity = {
        ...taskData,
        name: data.name,
        type: data.executor,
        parameters: config,
        settings: data.settings,
      } as Activity

      updateActivity(nodeId, updatedActivity)
      onClose()
    } catch (error) {
      showError({
        title: 'Update failed',
        description: error instanceof Error ? error.message : 'Failed to update step',
      })
    }
  }

  return (
    <ActionNodeForm
      initialData={initialData}
      onSubmit={handleSubmit}
      onHeaderContentChange={onHeaderContentChange}
      projectId={projectId}
    />
  )
}
