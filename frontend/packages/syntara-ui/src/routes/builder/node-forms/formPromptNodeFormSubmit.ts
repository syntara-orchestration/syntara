import { resolveEffectiveContinueOnFailure } from '../hooks/useEffectiveContinueOnFailure'

import type { FormPromptFormSubmitData } from './FormPromptNodeForm'
import type { FormPromptFormData } from './formPromptNodeFormSchema'
import { persistNodeSettings } from './shared/nodeSettingsSchema'

export function mapFormPromptFormDataToSubmit(
  data: FormPromptFormData,
  systemContinueOnFailure: boolean | null
): FormPromptFormSubmitData {
  const submitLabel = data.submit_label?.trim()
  const successMessage = data.success_message?.trim()
  const timezone = data.timezone?.trim()
  const cssOverride = data.css_override?.trim()

  const effectiveCof = resolveEffectiveContinueOnFailure(data.settings?.continue_on_failure, systemContinueOnFailure)
  const fallbackDecision = effectiveCof.isEffectivelyEnabled ? (data.fallback_decision ?? 'fallback') : 'submit'

  return {
    name: data.name.trim(),
    message: data.message?.trim() || null,
    form_definition: data.form_definition,
    responder_users: data.responder_users && data.responder_users.length > 0 ? data.responder_users : undefined,
    responder_groups: data.responder_groups && data.responder_groups.length > 0 ? data.responder_groups : undefined,
    response_window: data.response_window ?? null,
    fallback_decision: fallbackDecision,
    ...(submitLabel ? { submit_label: submitLabel } : {}),
    ...(successMessage ? { success_message: successMessage } : {}),
    ...(timezone ? { timezone } : {}),
    ...(cssOverride ? { css_override: cssOverride } : {}),
    settings: persistNodeSettings(data.settings),
  }
}
