import type { FormPromptFormSubmitData } from './FormPromptNodeForm'
import type { FormPromptFormData } from './formPromptNodeFormSchema'
import { persistStepSettings } from './shared/stepSettingsSchema'

export function mapFormPromptFormDataToSubmit(data: FormPromptFormData): FormPromptFormSubmitData {
  const submitLabel = data.submit_label?.trim()
  const successMessage = data.success_message?.trim()
  const cssOverride = data.css_override?.trim()
  const fallbackDecision = data.fallback_decision ?? 'fallback'

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
    ...(cssOverride ? { css_override: cssOverride } : {}),
    settings: persistStepSettings(data.settings),
  }
}
