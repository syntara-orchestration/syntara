/** API parameter `parameters.fallback_behavior` for form_prompt nodes. */
export type FormPromptFallbackBehavior = 'fail' | 'fallback'

export function formPromptFallbackBehaviorFromDecision(
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
  const nodeCof = settings?.continue_on_failure
  const effectiveCof = nodeCof === true || nodeCof === false ? Boolean(nodeCof) : systemContinueOnFailure
  if (effectiveCof && parameters.fallback_decision === 'fallback') {
    return 'fallback'
  }
  return 'fail'
}
