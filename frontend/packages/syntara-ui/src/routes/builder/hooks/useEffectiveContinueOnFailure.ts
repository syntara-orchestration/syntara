import { useFormContext, useWatch } from 'react-hook-form'

import { useWorkflowEngineDefaults } from './useWorkflowEngineDefaults'

type FormWithContinueOnFailure = {
  settings?: { continue_on_failure?: boolean }
}

/** Where the effective continue-on-failure value came from. */
export type ContinueOnFailureSource = 'node-explicit' | 'admin-default' | 'system-fallback'

export type EffectiveContinueOnFailure = {
  /** True when the engine would apply continue-on-failure for this node. */
  isEffectivelyEnabled: boolean
  /** Resolution source matching engine order: node setting, then admin default, then false. */
  source: ContinueOnFailureSource
}

/**
 * Resolves effective continue-on-failure the same way the workflow engine does:
 * `node.settings.continue_on_failure ?? admin default ?? false`.
 */
export function resolveEffectiveContinueOnFailure(
  nodeContinueOnFailure: boolean | undefined | null,
  adminDefault: boolean | null
): EffectiveContinueOnFailure {
  if (nodeContinueOnFailure === true) {
    return { isEffectivelyEnabled: true, source: 'node-explicit' }
  }
  if (nodeContinueOnFailure === false) {
    return { isEffectivelyEnabled: false, source: 'node-explicit' }
  }
  if (adminDefault === true) {
    return { isEffectivelyEnabled: true, source: 'admin-default' }
  }
  if (adminDefault === false) {
    return { isEffectivelyEnabled: false, source: 'admin-default' }
  }
  return { isEffectivelyEnabled: false, source: 'system-fallback' }
}

/**
 * Watches the node form's continue-on-failure setting and the admin default,
 * then returns the engine-equivalent effective value.
 */
export function useEffectiveContinueOnFailure(): EffectiveContinueOnFailure {
  const { control } = useFormContext<FormWithContinueOnFailure>()
  const nodeContinueOnFailure = useWatch({ control, name: 'settings.continue_on_failure' })
  const { defaults } = useWorkflowEngineDefaults()
  return resolveEffectiveContinueOnFailure(nodeContinueOnFailure, defaults?.continueOnFailure ?? null)
}
