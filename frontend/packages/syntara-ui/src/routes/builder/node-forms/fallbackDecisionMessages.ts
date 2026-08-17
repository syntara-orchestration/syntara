import type { ContinueOnFailureSource } from '../hooks/useEffectiveContinueOnFailure'

import {
  APPROVAL_FALLBACK_DISABLED_EXPLICIT_STOP,
  APPROVAL_FALLBACK_DISABLED_SYSTEM_DEFAULT,
} from './shared/nodeFieldHelpText'

/** Warning copy when Fallback decision is disabled because continue on failure is off. */
export function getFallbackDecisionDisabledMessage(
  isEffectivelyEnabled: boolean,
  source: ContinueOnFailureSource
): string | undefined {
  if (isEffectivelyEnabled) return undefined
  if (source === 'node-explicit') return APPROVAL_FALLBACK_DISABLED_EXPLICIT_STOP
  return APPROVAL_FALLBACK_DISABLED_SYSTEM_DEFAULT
}
