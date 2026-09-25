import { createEmptyFormDefinition } from '../../../components/forms/formFieldBuilder/createDefaultField'
import { formPromptFallbackDecisionFromBehavior } from '../utils/formPromptFallbackBehavior'

import type { FormPromptFormSubmitData } from './FormPromptNodeForm'
import type { FormPromptFormData } from './formPromptNodeFormSchema'

export function getFormPromptNodeFormDefaultValues(
  initialData?: Partial<FormPromptFormSubmitData>
): FormPromptFormData {
  const {
    name = '',
    message = '',
    form_definition,
    responder_users = [],
    responder_groups = [],
    response_window,
    fallback_decision,
    fallback_behavior,
    submit_label = 'Submit',
    success_message = 'Response submitted successfully.',
    timezone = 'UTC',
    css_override = '',
    settings = {},
  } = initialData ?? {}

  return {
    name,
    message: message ?? '',
    form_definition: (form_definition ?? createEmptyFormDefinition()) as FormPromptFormData['form_definition'],
    responder_users,
    responder_groups,
    response_window: response_window ?? undefined,
    fallback_decision: fallback_decision ?? formPromptFallbackDecisionFromBehavior(fallback_behavior),
    submit_label: submit_label ?? undefined,
    success_message: success_message ?? undefined,
    timezone: timezone ?? undefined,
    css_override: css_override ?? '',
    settings,
  }
}
