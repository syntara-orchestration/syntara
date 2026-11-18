import type { WorkflowAPI } from '@syntara/contracts'

/**
 * Form ↔ workflow mapping for Script node Execution Plane placement.
 *
 * Affinity "none" → omit / clear execution_profile (EP picks the default target).
 * Affinity "required_target" → { type: 'execution_target', execution_target_id }.
 */

export const ScriptAffinityEnum = {
  NONE: 'none',
  REQUIRED_TARGET: 'required_target',
} as const

export type ScriptAffinity = (typeof ScriptAffinityEnum)[keyof typeof ScriptAffinityEnum]

export type ExecutionTargetProfile = WorkflowAPI.components['schemas']['ExecutionTargetProfile']

export type ScriptExecutionFormFields = {
  affinity: ScriptAffinity
  execution_target_id?: string
}

function isExecutionTargetProfile(value: unknown): value is ExecutionTargetProfile {
  if (typeof value !== 'object' || value === null) {
    return false
  }
  const profile = value as { type?: unknown; execution_target_id?: unknown }
  return profile.type === 'execution_target' && typeof profile.execution_target_id === 'string'
}

/** Hydrate form affinity fields from stored script parameters. */
export function parseScriptExecutionFormFields(parameters: Record<string, unknown>): ScriptExecutionFormFields {
  const profile = parameters.execution_profile
  if (!isExecutionTargetProfile(profile) || !profile.execution_target_id.trim()) {
    return { affinity: ScriptAffinityEnum.NONE }
  }
  return {
    affinity: ScriptAffinityEnum.REQUIRED_TARGET,
    execution_target_id: profile.execution_target_id,
  }
}

/** Build execution_profile for script parameters, or undefined when affinity is none. */
export function buildScriptExecutionProfile(
  affinity: ScriptAffinity | undefined,
  executionTargetId: string | undefined
): ExecutionTargetProfile | undefined {
  if (affinity !== ScriptAffinityEnum.REQUIRED_TARGET) {
    return undefined
  }
  const trimmedId = executionTargetId?.trim()
  if (!trimmedId) {
    return undefined
  }
  return {
    type: 'execution_target',
    execution_target_id: trimmedId,
  }
}
