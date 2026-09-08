import { createAAPJobTemplateActivity, createAAPWorkflowTemplateActivity } from '../../../stores/useWorkflowStore'
import type { AAPJobTemplateConfig, AAPWorkflowTemplateConfig } from '../../../stores/workflowFactories'
import type { AAPJobTemplateFormData } from '../node-forms/aapJobTemplateSchema'
import type { AAPWorkflowTemplateFormData } from '../node-forms/aapWorkflowTemplateSchema'

/**
 * Check whether any of the given values contain a ${...} expression placeholder.
 * Used to detect expression mode in AAP forms.
 */
export function hasExpressionValue(...values: (string | undefined)[]): boolean {
  return values.some((v) => v?.includes('${'))
}

/** True when the job template form is in input-variables (expression) mode. */
export function isJobTemplateInputVariablesMode(
  data: Pick<AAPJobTemplateFormData, 'use_input_variables' | 'organization_name' | 'job_template_name'>
): boolean {
  return Boolean(data.use_input_variables) || hasExpressionValue(data.organization_name, data.job_template_name)
}

/**
 * Build an AAP activity in expression mode (template name/org provided as expressions
 * that resolve at runtime rather than a concrete job_template_id).
 */
export function buildExpressionModeActivity(
  nodeId: string,
  name: string,
  data: AAPJobTemplateFormData
): ReturnType<typeof createAAPJobTemplateActivity> {
  // job_template_id is set to 0 as a placeholder — expression-mode nodes resolve
  // the template by name at runtime, so the ID is removed from config below.
  const config = { ...buildAAPConfig(data), useInputVariables: true }
  const activity = createAAPJobTemplateActivity(nodeId, name, 0, config)
  if (activity.parameters) {
    activity.parameters.job_template_name = data.job_template_name
    activity.parameters.organization_name = data.organization_name
    delete activity.parameters.job_template_id
  }
  return activity
}

/**
 * Validates that a job template ID is a valid positive integer.
 * @param jobTemplateId - The ID to validate
 * @returns The validated ID
 * @throws Error if validation fails
 */
export function validateJobTemplateId(jobTemplateId: number | undefined): number {
  if (!jobTemplateId || !Number.isInteger(jobTemplateId) || jobTemplateId < 1) {
    throw new Error('Job Template ID must be a valid positive integer')
  }
  return jobTemplateId
}

/**
 * Parse and validate a positive integer from a string
 */
function parsePositiveInt(value: string, min = 1): number | undefined {
  const parsed = Number.parseInt(value, 10)
  return !Number.isNaN(parsed) && parsed >= min ? parsed : undefined
}

/**
 * Parse and validate JSON extra variables
 */
function parseExtraVars(value: string): Record<string, unknown> | undefined {
  try {
    const parsed: unknown = JSON.parse(value)
    return typeof parsed === 'object' && parsed !== null && !Array.isArray(parsed)
      ? (parsed as Record<string, unknown>)
      : undefined
  } catch {
    return undefined
  }
}

type ConfigKey = keyof AAPJobTemplateConfig

/**
 * Table-driven mapping from form fields to config fields.
 * Each entry: [formKey, configKey, predicate] — predicate determines whether to include.
 */
const stringFields: [keyof AAPJobTemplateFormData, ConfigKey][] = [
  ['limit', 'limit'],
  ['tags', 'tags'],
  ['skip_tags', 'skipTags'],
  ['job_type', 'jobType'],
]

const numberFields: [keyof AAPJobTemplateFormData, ConfigKey][] = [
  ['forks', 'forks'],
  ['job_slice_count', 'jobSlicing'],
]

function collectStringFields(config: AAPJobTemplateConfig, data: AAPJobTemplateFormData): void {
  for (const [formKey, configKey] of stringFields) {
    const value = data[formKey]
    if (typeof value === 'string' && value) {
      ;(config as Record<string, unknown>)[configKey] = value
    }
  }
}

function collectNumberFields(config: AAPJobTemplateConfig, data: AAPJobTemplateFormData): void {
  for (const [formKey, configKey] of numberFields) {
    const value = data[formKey]
    if (typeof value === 'number' && Number.isFinite(value)) {
      ;(config as Record<string, unknown>)[configKey] = value
    }
  }
}

function setOrganizationAndTemplate(config: AAPJobTemplateConfig, data: AAPJobTemplateFormData): void {
  // Organization ID (takes precedence over name)
  if (data.organization_id !== undefined && data.organization_id !== null) {
    config.organizationId = data.organization_id
  }
  // Organization name (for lookup if ID not provided)
  if (data.organization_name) config.organization = data.organization_name
  if (data.job_template_name) config.jobTemplateName = data.job_template_name
}

function setInventoryFields(config: AAPJobTemplateConfig, data: AAPJobTemplateFormData): void {
  if (data.inventory_id !== undefined && data.inventory_id !== null) {
    config.inventory = data.inventory_id
  }
  if (data.inventory_name) config.inventoryName = data.inventory_name
}

function setExecutionEnvironmentFields(config: AAPJobTemplateConfig, data: AAPJobTemplateFormData): void {
  if (data.execution_environment_id !== undefined && data.execution_environment_id !== null) {
    config.executionEnvironmentId = data.execution_environment_id
  }
  if (data.execution_environment) config.executionEnvironment = data.execution_environment
}

function setExtraVarsField(config: AAPJobTemplateConfig, data: AAPJobTemplateFormData): void {
  if (!data.extra_vars) return
  const extraVars = parseExtraVars(data.extra_vars)
  if (extraVars) config.extraVars = extraVars
}

function setVerbosityField(config: AAPJobTemplateConfig, data: AAPJobTemplateFormData): void {
  if (!data.verbosity) return
  const verbosity = parsePositiveInt(data.verbosity, 0)
  if (verbosity !== undefined && verbosity <= 5) config.verbosity = verbosity
}

function setCredentialFields(config: AAPJobTemplateConfig, data: AAPJobTemplateFormData): void {
  if (data.credential_id) config.credentialId = data.credential_id
  if (data.integration_id) config.integrationId = data.integration_id
  if (data.job_credentials && data.job_credentials.length > 0) {
    config.jobCredentials = data.job_credentials
  }
}

function setLabelsField(config: AAPJobTemplateConfig, data: AAPJobTemplateFormData): void {
  // Labels are an array of label names (strings) - AAP supports creating new labels
  if (data.labels && data.labels.length > 0) {
    config.labels = data.labels
  }
}

function setDiffModeField(config: AAPJobTemplateConfig, data: AAPJobTemplateFormData): void {
  if (data.diff_mode !== undefined) config.diffMode = data.diff_mode
}

function setUseInputVariablesField(config: AAPJobTemplateConfig, data: AAPJobTemplateFormData): void {
  if (data.use_input_variables) config.useInputVariables = true
}

function setInstanceGroupFields(config: AAPJobTemplateConfig, data: AAPJobTemplateFormData): void {
  // Instance group ID (takes precedence over name)
  if (data.instance_group_id !== undefined && data.instance_group_id !== null) {
    config.instanceGroupId = data.instance_group_id
  }
  // Instance group name (for lookup if ID not provided)
  if (data.instance_group) {
    config.instanceGroupName = data.instance_group
  }
}

/**
 * Build optional AAP job configuration from form data.
 * The jobTemplateId and organization are handled separately by the caller.
 */
export function buildAAPConfig(data: AAPJobTemplateFormData): AAPJobTemplateConfig | undefined {
  const config: AAPJobTemplateConfig = {}

  setOrganizationAndTemplate(config, data)
  setInventoryFields(config, data)
  setExecutionEnvironmentFields(config, data)
  setExtraVarsField(config, data)
  setVerbosityField(config, data)
  setCredentialFields(config, data)
  setLabelsField(config, data)
  setDiffModeField(config, data)
  setInstanceGroupFields(config, data)
  setUseInputVariablesField(config, data)
  collectStringFields(config, data)
  collectNumberFields(config, data)

  return Object.keys(config).length > 0 ? config : undefined
}

// ── Workflow Template Helpers ──────────────────────────────────────────

/**
 * Validates that a workflow template ID is a valid positive integer.
 * @param workflowTemplateId - The ID to validate
 * @returns The validated ID
 * @throws Error if validation fails
 */
export function validateWorkflowTemplateId(workflowTemplateId: number | undefined): number {
  if (!workflowTemplateId || !Number.isInteger(workflowTemplateId) || workflowTemplateId < 1) {
    throw new Error('Workflow Template ID must be a valid positive integer')
  }
  return workflowTemplateId
}

/**
 * Build an AAP workflow template activity in expression mode.
 */
export function buildWorkflowExpressionModeActivity(
  nodeId: string,
  name: string,
  data: AAPWorkflowTemplateFormData
): ReturnType<typeof createAAPWorkflowTemplateActivity> {
  const config = buildAAPWorkflowTemplateConfig(data)
  const activity = createAAPWorkflowTemplateActivity(nodeId, name, 0, config)
  if (activity.parameters) {
    activity.parameters.workflow_job_template_name = data.workflow_job_template_name
    activity.parameters.organization_name = data.organization_name
    delete activity.parameters.workflow_job_template_id
  }
  return activity
}

/**
 * Build optional AAP workflow template configuration from form data.
 * Workflow templates support: inventory, limit, scm_branch, labels, tags, skip_tags, extra_vars.
 * They do NOT support job-specific fields like job_type, verbosity, forks, etc.
 */
export function buildAAPWorkflowTemplateConfig(
  data: AAPWorkflowTemplateFormData
): AAPWorkflowTemplateConfig | undefined {
  const config: AAPWorkflowTemplateConfig = {}

  setWorkflowOrganizationAndTemplate(config, data)
  setWorkflowInventoryFields(config, data)
  setWorkflowCredentialField(config, data)
  setWorkflowLabelsField(config, data)
  setWorkflowExtraVarsField(config, data)
  setWorkflowPromptOverrides(config, data)

  return Object.keys(config).length > 0 ? config : undefined
}

function setWorkflowOrganizationAndTemplate(
  config: AAPWorkflowTemplateConfig,
  data: AAPWorkflowTemplateFormData
): void {
  if (data.organization_id !== undefined && data.organization_id !== null) {
    config.organization_id = data.organization_id
  }
  if (data.organization_name) config.organization_name = data.organization_name
  if (data.workflow_job_template_name) config.workflow_job_template_name = data.workflow_job_template_name
}

function setWorkflowInventoryFields(config: AAPWorkflowTemplateConfig, data: AAPWorkflowTemplateFormData): void {
  if (data.inventory_id !== undefined && data.inventory_id !== null) {
    config.inventory_id = data.inventory_id
  }
  if (data.inventory_name) config.inventory_name = data.inventory_name
}

function setWorkflowCredentialField(config: AAPWorkflowTemplateConfig, data: AAPWorkflowTemplateFormData): void {
  if (data.credential_id) config.credential_id = data.credential_id
  if (data.integration_id) config.integration_id = data.integration_id
}

function setWorkflowLabelsField(config: AAPWorkflowTemplateConfig, data: AAPWorkflowTemplateFormData): void {
  // Workflow templates support label overrides (array of label names)
  if (data.labels?.length) config.labels = data.labels
}

function setWorkflowExtraVarsField(config: AAPWorkflowTemplateConfig, data: AAPWorkflowTemplateFormData): void {
  if (data.extra_vars) {
    const extraVars = parseExtraVars(data.extra_vars)
    if (extraVars) config.extra_vars = extraVars
  }
}

function setWorkflowPromptOverrides(config: AAPWorkflowTemplateConfig, data: AAPWorkflowTemplateFormData): void {
  // String fields specific to workflows: limit, scm_branch, tags, skip_tags
  if (data.limit) config.limit = data.limit
  if (data.scm_branch) config.scm_branch = data.scm_branch
  if (data.tags) config.tags = data.tags
  if (data.skip_tags) config.skip_tags = data.skip_tags
}
