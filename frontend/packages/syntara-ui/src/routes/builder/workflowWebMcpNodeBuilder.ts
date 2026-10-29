import type { Activity } from '@syntara/contracts'

import { generateActivityId } from '../../utils/generateUUID'

import { WEBMCP_WORKFLOW_NODE_TYPES, cleanText, copyParameterObject, findSupportedType } from './workflowWebMcp'
import { parseNodeSettings } from './workflowWebMcpSettings'

function isRecord(value: unknown): value is Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return false
  const prototype = Object.getPrototypeOf(value) as unknown
  return prototype === Object.prototype || prototype === null
}

export function buildWorkflowNodeActivity(input: unknown): Activity {
  if (!isRecord(input)) throw new Error('Workflow node input must be an object.')
  const type = findSupportedType(WEBMCP_WORKFLOW_NODE_TYPES, input.type)
  if (!type) throw new Error('Workflow node type is not supported.')
  const name = cleanText(input.name, 'Node name', 255)
  const parameters = input.parameters === undefined ? {} : copyParameterObject(input.parameters, 'Node parameters')
  const settings = parseNodeSettings(input.settings, 'Node settings')
  return {
    id: generateActivityId(),
    type,
    name,
    parameters,
    ...(settings && { settings }),
  }
}

function resolveUpdatedNodeType(current: Activity, input: Record<string, unknown>) {
  const type = Object.hasOwn(input, 'type') ? findSupportedType(WEBMCP_WORKFLOW_NODE_TYPES, input.type) : current.type
  if (!type) throw new Error('Workflow node type is not supported.')
  const typeChanged = type !== current.type
  if (typeChanged && !Object.hasOwn(input, 'parameters')) {
    throw new Error('Provide a full parameters object when changing the node type.')
  }
  if (Object.hasOwn(input, 'parameters') && Object.hasOwn(input, 'parameters_patch')) {
    throw new Error('Provide parameters or parameters_patch, not both.')
  }
  return { type, typeChanged }
}

function resolveNodeParameterUpdates(
  current: Activity,
  input: Record<string, unknown>
): Pick<Partial<Activity>, 'parameters'> {
  if (Object.hasOwn(input, 'parameters')) {
    return { parameters: copyParameterObject(input.parameters, 'Node parameters') }
  }
  if (Object.hasOwn(input, 'parameters_patch')) {
    const patch = copyParameterObject(input.parameters_patch, 'Node parameters patch')
    return { parameters: { ...(current.parameters ?? {}), ...patch } }
  }
  return {}
}

function resolveNodeSettingsUpdate(
  current: Activity,
  input: Record<string, unknown>
): Pick<Partial<Activity>, 'settings'> {
  if (!Object.hasOwn(input, 'settings_patch')) return {}
  const patch = parseNodeSettings(input.settings_patch, 'Node settings patch')
  if (!patch) throw new Error('Node settings patch must be an object.')
  return {
    settings: {
      ...current.settings,
      ...patch,
      ...(patch.retry_policy && {
        retry_policy: { ...current.settings?.retry_policy, ...patch.retry_policy },
      }),
    },
  }
}

export function buildWorkflowNodeUpdate(current: Activity, input: unknown): Partial<Activity> {
  if (!isRecord(input)) throw new Error('Workflow node updates must be an object.')
  const allowedKeys = new Set(['node_id', 'type', 'name', 'parameters', 'parameters_patch', 'settings_patch'])
  for (const key of Object.keys(input)) {
    if (!allowedKeys.has(key)) throw new Error(`Workflow node update field "${key}" is not supported.`)
  }

  const { type, typeChanged } = resolveUpdatedNodeType(current, input)
  const updates: Partial<Activity> = {
    ...resolveNodeParameterUpdates(current, input),
    ...resolveNodeSettingsUpdate(current, input),
  }
  if (typeChanged) updates.type = type
  if (Object.hasOwn(input, 'name')) updates.name = cleanText(input.name, 'Node name', 255)
  if (Object.keys(updates).length === 0) throw new Error('Provide at least one field to update.')
  return updates
}
