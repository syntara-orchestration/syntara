import type { FormDefinition, FormField } from '@syntara/contracts'

import { FormFieldTypeEnum } from './formFieldTypeEnum'

function fieldHasUnresolvedDynamicOptions(field: FormField): boolean {
  if (field.type !== FormFieldTypeEnum.DROPDOWN && field.type !== FormFieldTypeEnum.MULTI_SELECT) {
    return false
  }
  return field.options.source === 'dynamic'
}

/** True when the definition still references upstream expressions (not yet materialized by the workflow). */
export function formDefinitionHasUnresolvedDynamicOptions(definition: FormDefinition): boolean {
  return definition.fields.some(fieldHasUnresolvedDynamicOptions)
}

export const FORM_PROMPT_UNRESOLVED_DYNAMIC_OPTIONS_ALERT_TITLE = 'Dynamic options unavailable'

export const FORM_PROMPT_UNRESOLVED_DYNAMIC_OPTIONS_ALERT_BODY =
  'This form prompt still references dynamic option expressions. Reload the page or contact an administrator if dropdown options do not appear.'

export const FORM_PROMPT_PREVIEW_DYNAMIC_OPTIONS_ALERT_TITLE = 'Dynamic options not shown in preview'

export const FORM_PROMPT_PREVIEW_DYNAMIC_OPTIONS_ALERT_BODY =
  'Options populated from upstream workflow output appear when the form prompt runs. Preview cannot resolve those expressions without execution context.'
