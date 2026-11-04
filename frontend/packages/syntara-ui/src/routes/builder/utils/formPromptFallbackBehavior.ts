import { resolveEffectiveContinueOnFailure } from '../hooks/useEffectiveContinueOnFailure'

/** Derived routing mode for client validation (not persisted — backend uses `fallback_decision`). */
export type FormPromptFallbackBehavior = 'fail' | 'fallback'

function formPromptFallbackBehaviorFromDecision(
  fallbackDecision: 'submit' | 'fallback' | null | undefined
): FormPromptFallbackBehavior {
  return fallbackDecision === 'fallback' ? 'fallback' : 'fail'
}

export function formPromptFallbackDecisionFromBehavior(
  fallbackBehavior: string | null | undefined
): 'submit' | 'fallback' {
  return fallbackBehavior === 'fallback' ? 'fallback' : 'submit'
}

/** Match backend `_resolve_form_prompt_fallback_behavior` for validation. */
export function resolveFormPromptFallbackBehavior(
  parameters: Record<string, unknown>,
  settings: Record<string, unknown> | undefined,
  systemContinueOnFailure: boolean
): FormPromptFallbackBehavior {
  const explicit = parameters.fallback_behavior
  if (explicit === 'fail' || explicit === 'fallback') {
    return explicit
  }
  const decision = parameters.fallback_decision
  if (decision === 'submit' || decision === 'fallback') {
    return formPromptFallbackBehaviorFromDecision(decision)
  }
  const { isEffectivelyEnabled } = resolveEffectiveContinueOnFailure(
    settings?.continue_on_failure as boolean | undefined | null,
    systemContinueOnFailure
  )
  if (isEffectivelyEnabled && parameters.fallback_decision === 'fallback') {
    return 'fallback'
  }
  return 'fail'
}
