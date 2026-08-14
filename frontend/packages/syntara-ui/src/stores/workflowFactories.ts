import { ActivityTypeEnum, EdgeHandleEnum, type Activity, type NodeSettings } from '@syntara/contracts'

import { PROTOTYPE_POLLUTION_KEYS, safeJSONReviver } from '../utils/jsonSafeParse'
import { parseJsonEnvironment } from '../utils/parseJsonEnvironment'

import type { ActivityWithMetadata } from './workflowStoreTypes'

export {
  createEdaTrigger,
  createEventTrigger,
  createManualTrigger,
  createScheduledTrigger,
  createWebhookTrigger,
} from './triggerFactories'

// ============================================================================
// V2 Workflow Entity Factory Functions
// ============================================================================

/** Copy non-empty values from source to target. Skips undefined, null, empty strings, and non-finite numbers. */
function copyDefinedValues(source: Record<string, unknown>, target: Record<string, unknown>) {
  for (const [key, value] of Object.entries(source)) {
    if (value == null || (typeof value === 'number' && !Number.isFinite(value)) || value === '') continue
    target[key] = value
  }
}

// ============================================================================
// Executor Node Factory Functions
// ============================================================================

export type CreateScriptActivityOptions = {
  id: string
  name: string
  language?: string
  code?: string
  credentialId?: string
  environment?: string
  settings?: NodeSettings
}

/** Create a script node (v2). */
export function createScriptActivity(options: CreateScriptActivityOptions): Activity {
  const { id, name, language, code, credentialId, environment, settings } = options
  const parsedEnvironment = parseJsonEnvironment(environment)

  return {
    id,
    type: ActivityTypeEnum.SCRIPT,
    name,
    parameters: {
      ...(language !== undefined && { language }),
      ...(code !== undefined && { code }),
      ...(credentialId && { credential_id: credentialId }),
      ...(parsedEnvironment && { environment: parsedEnvironment }),
    },
    ...(settings && { settings }),
  }
}

export type CreateApiActivityOptions = {
  id: string
  name: string
  method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE'
  url?: string
  headers?: Array<{ id: string; key: string; value: string }>
  body?: string
  inputs?: string
  credentialId?: string
  settings?: NodeSettings
}

function headersEntriesToRecord(entries: Array<{ key: string; value: string }> | undefined) {
  if (!entries?.length) return undefined
  const safe = entries.filter(({ key }) => key.trim() && !PROTOTYPE_POLLUTION_KEYS.has(key.trim()))
  if (!safe.length) return undefined
  return Object.fromEntries(safe.map(({ key, value }) => [key.trim(), value])) as Record<string, string>
}

/** Create an HTTP request node (v2). */
export function createApiActivity(options: CreateApiActivityOptions): Activity {
  const { id, name, method, url, headers, body, credentialId, settings } = options
  const config: Record<string, unknown> = {
    ...(method !== undefined && { method }),
    ...(url !== undefined && { url }),
  }

  const headerRecord = headersEntriesToRecord(headers)
  if (headerRecord) {
    config.headers = headerRecord
  }

  if (body) {
    try {
      // SECURITY: Use reviver to strip prototype pollution keys
      config.body = JSON.parse(body, safeJSONReviver) as unknown
    } catch {
      config.body = body
    }
  }

  return {
    id,
    type: ActivityTypeEnum.HTTP_REQUEST,
    name,
    parameters: {
      ...config,
      ...(credentialId && { credential_id: credentialId }),
    },
    ...(settings && { settings }),
  }
}

export type CreateAgenticActivityOptions = {
  id: string
  name: string
  toolSelectionStrategy?: 'ALL' | 'NONE' | 'SELECTED'
  toolSelections?: string[]
  integrationConnections?: { integration_id: string; credential_id: string }[]
  prompt?: string
  llmModelId?: string
  inputs?: string
  fileIds?: string[]
  credentialId?: string
  responseSchema?: Record<string, unknown>
  settings?: NodeSettings
}

/**
 * Create an agentic node (v2).
 */
export function createAgenticActivity(options: CreateAgenticActivityOptions): Activity {
  const {
    id,
    name,
    toolSelectionStrategy,
    toolSelections,
    integrationConnections,
    prompt,
    llmModelId,
    fileIds,
    credentialId,
    responseSchema,
    settings,
  } = options
  const config: Record<string, unknown> = {}

  if (prompt) config.prompt = prompt
  if (llmModelId) config.llm_model_id = llmModelId

  if (toolSelectionStrategy !== undefined) {
    config.tool_selection_strategy = toolSelectionStrategy
    if (toolSelectionStrategy === 'SELECTED' && toolSelections?.length) {
      config.tool_selections = toolSelections
    }
  }

  if (integrationConnections && integrationConnections.length > 0)
    config.integration_connections = integrationConnections
  if (fileIds && fileIds.length > 0) config.file_ids = fileIds
  if (credentialId) config.credential_id = credentialId
  if (responseSchema) config.response_schema = responseSchema

  return {
    id,
    type: ActivityTypeEnum.AGENTIC,
    name,
    parameters: config,
    ...(settings && { settings }),
  }
}

/**
 * AAP Job Template config — matches the backend AAPJobTemplateExecutorConfig fields.
 */
export type AAPJobTemplateConfig = {
  credentialId?: string
  integrationId?: string
  organizationId?: number
  organization?: string
  jobTemplateName?: string
  inventory?: number
  inventoryName?: string
  extraVars?: Record<string, unknown>
  limit?: string
  tags?: string
  skipTags?: string
  verbosity?: number
  jobCredentials?: number[] // AAP Controller credential IDs for job execution (prompt-on-launch override)
  jobType?: string
  forks?: number
  jobSlicing?: number
  diffMode?: boolean
  executionEnvironment?: string
  executionEnvironmentId?: number
  instanceGroupId?: number
  instanceGroupName?: string
  labels?: string[] // AAP Controller label names (prompt-on-launch override, supports creating new labels)
}

/** Mapping from AAPJobTemplateConfig key → API config key, with a predicate type. */
const aapConfigMapping: [keyof AAPJobTemplateConfig, string, 'truthy' | 'defined'][] = [
  ['credentialId', 'credential_id', 'truthy'],
  ['integrationId', 'integration_id', 'truthy'],
  ['organizationId', 'organization_id', 'defined'],
  ['organization', 'organization_name', 'truthy'],
  ['jobTemplateName', 'job_template_name', 'truthy'],
  ['inventory', 'inventory_id', 'defined'],
  ['inventoryName', 'inventory_name', 'truthy'],
  ['extraVars', 'extra_vars', 'truthy'],
  ['limit', 'limit', 'truthy'],
  ['tags', 'tags', 'truthy'],
  ['skipTags', 'skip_tags', 'truthy'],
  ['verbosity', 'verbosity', 'defined'],
  ['jobCredentials', 'job_credentials', 'defined'],
  ['jobType', 'job_type', 'truthy'],
  ['forks', 'forks', 'defined'],
  ['jobSlicing', 'job_slice_count', 'defined'],
  ['diffMode', 'diff_mode', 'defined'],
  ['executionEnvironment', 'execution_environment', 'truthy'],
  ['executionEnvironmentId', 'execution_environment_id', 'defined'],
  ['instanceGroupId', 'instance_group_id', 'defined'],
  ['instanceGroupName', 'instance_group_name', 'truthy'],
  ['labels', 'labels', 'truthy'],
]

/**
 * Create an AAP Job Template node (v2).
 */
export function createAAPJobTemplateActivity(
  id: string,
  name: string,
  jobTemplateId?: number,
  config?: AAPJobTemplateConfig,
  settings?: NodeSettings
): Activity {
  const activityConfig: Record<string, unknown> = {
    ...(jobTemplateId !== undefined && { job_template_id: jobTemplateId }),
  }

  if (config) {
    for (const [srcKey, destKey, predicate] of aapConfigMapping) {
      const value = config[srcKey]
      const include =
        predicate === 'defined'
          ? value !== undefined && (typeof value !== 'number' || Number.isFinite(value))
          : Boolean(value)
      if (include) {
        activityConfig[destKey] = value
      }
    }
  }

  return {
    id,
    type: ActivityTypeEnum.AAP_JOB_TEMPLATE,
    name,
    parameters: activityConfig,
    ...(settings && { settings }),
  }
}

/**
 * AAP Workflow Template config — matches the backend AAPWorkflowTemplateExecutorConfig fields.
 * Workflow templates do NOT support job-specific fields like job_type, verbosity, forks, etc.
 * Timeout is configured via node settings, not here.
 */
export type AAPWorkflowTemplateConfig = {
  credential_id?: string
  integration_id?: string
  organization_id?: number
  organization_name?: string
  workflow_job_template_name?: string
  inventory_id?: number
  inventory_name?: string
  extra_vars?: Record<string, unknown>
  limit?: string
  scm_branch?: string // Workflow-specific: source control branch override
  tags?: string
  skip_tags?: string
  labels?: string[] // AAP Controller label names (prompt-on-launch override, supports creating new labels)
}

/**
 * Create an AAP Workflow Template node (v2).
 */
export function createAAPWorkflowTemplateActivity(
  id: string,
  name: string,
  workflowTemplateId?: number,
  config?: AAPWorkflowTemplateConfig,
  settings?: NodeSettings
): Activity {
  const activityConfig: Record<string, unknown> = {
    ...(workflowTemplateId !== undefined && { workflow_job_template_id: workflowTemplateId }),
  }

  if (config) {
    copyDefinedValues(config, activityConfig)
  }

  return {
    id,
    type: ActivityTypeEnum.AAP_WORKFLOW_JOB_TEMPLATE,
    name,
    parameters: activityConfig,
    ...(settings && { settings }),
  }
}

// ============================================================================
// Approval Node Factory
// ============================================================================

export type CreateApprovalActivityOptions = {
  id: string
  name: string
  approver_users?: string[]
  approver_groups?: string[]
  prompt?: string
  fallback_decision?: 'approve' | 'reject'
  decision_window?: number
  settings?: Activity['settings']
}

/**
 * Create an approval node (v2).
 */
export function createApprovalActivity(options: CreateApprovalActivityOptions): Activity {
  const { id, name, approver_users, approver_groups, prompt, fallback_decision, decision_window, settings } = options
  return {
    id,
    type: ActivityTypeEnum.APPROVAL,
    name,
    parameters: {
      ...(prompt && { prompt }),
      ...(fallback_decision !== undefined && { fallback_decision }),
      ...(decision_window !== undefined && { decision_window }),
      ...(approver_users !== undefined && approver_users.length > 0 && { approver_users }),
      ...(approver_groups !== undefined && approver_groups.length > 0 && { approver_groups }),
    },
    ...(settings ? { settings } : {}),
  }
}

// ============================================================================
// Control Flow Node Factory Functions
// ============================================================================

/**
 * Create a condition node (v2).
 */
export function createConditionActivity(id: string, name: string, condition?: string): Activity {
  return {
    id,
    type: ActivityTypeEnum.CONDITION,
    name,
    parameters: {
      ...(condition !== undefined && { condition }),
    },
  }
}

/**
 * Create a loop node (v2).
 */
export function createLoopActivity(
  id: string,
  name: string,
  loopType: 'forEach' | 'while',
  config: {
    items?: string
    condition?: string
    maxIterations?: number
    indexVariable?: string
    itemVariable?: string
  },
  settings?: NodeSettings
): Activity {
  const maxIterations =
    config.maxIterations !== undefined && !Number.isNaN(config.maxIterations) ? config.maxIterations : undefined

  if (loopType === 'forEach') {
    return {
      id,
      type: ActivityTypeEnum.LOOP,
      name,
      parameters: {
        type: 'for_each',
        ...(config.items !== undefined && { items: config.items }),
        ...(config.itemVariable && { itemVariable: config.itemVariable }),
        ...(config.indexVariable && { indexVariable: config.indexVariable }),
        ...(maxIterations !== undefined && { max_iterations: maxIterations }),
      },
      ...(settings && { settings }),
    }
  }

  return {
    id,
    type: ActivityTypeEnum.LOOP,
    name,
    parameters: {
      type: 'do_while',
      ...(config.condition !== undefined && { condition: config.condition }),
      ...(maxIterations !== undefined && { max_iterations: maxIterations }),
    },
    ...(settings && { settings }),
  }
}

/**
 * Create a converge node (v2).
 */
export function createConvergeActivity(
  id: string,
  name: string,
  config?: {
    strategy?: 'all' | 'any'
    requiredPathCount?: number
    wait_duration?: number
  },
  settings?: NodeSettings
): Activity {
  return {
    id,
    type: ActivityTypeEnum.CONVERGE,
    name,
    parameters: {
      strategy: config?.strategy ?? 'all',
      ...(config?.strategy === 'any' && config?.requiredPathCount != null && { n_required: config.requiredPathCount }),
      ...(config?.wait_duration !== undefined && { wait_duration: config.wait_duration }),
    },
    ...(settings && { settings }),
  }
}

/**
 * Create a switch node (v2).
 */
export function createSwitchActivity(
  id: string,
  name: string,
  cases?: Array<{ port: string; label: string; condition?: string }>
): Activity {
  return {
    id,
    type: ActivityTypeEnum.SWITCH,
    name,
    parameters: {
      cases: cases ?? [],
      default_port: EdgeHandleEnum.DEFAULT,
    },
  }
}

/**
 * Create a wait node (v2).
 */
export function createWaitActivity(
  id: string,
  name: string,
  config: { duration: number },
  settings?: NodeSettings
): Activity {
  return {
    id,
    type: ActivityTypeEnum.WAIT,
    name,
    parameters: config,
    ...(settings && { settings }),
  }
}

/**
 * Create a generic placeholder node (v2).
 * UI-only concept — not backed by a v2 backend schema.
 * Metadata is stored in the `metadata` field (not `config`) for proper detection.
 *
 * SECURITY: Uses ActivityWithMetadata type instead of unsafe `as Activity` cast.
 * Metadata properties are restricted to the allowlist defined in ActivityMetadata interface.
 */
export function createGenericActivity(
  id: string,
  name: string = 'New Step',
  customMessage?: string
): ActivityWithMetadata {
  return {
    id,
    type: 'generic',
    name,
    parameters: {},
    metadata: {
      __isGeneric: true,
      ...(customMessage ? { __customMessage: customMessage } : {}),
    },
  }
}
