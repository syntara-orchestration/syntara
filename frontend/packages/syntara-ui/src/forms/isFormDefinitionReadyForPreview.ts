import type { FormDefinition } from '@syntara/contracts'

import { prepareFormDefinitionForCommit } from './dateFieldUtils'
import { safeParseFormDefinition } from './formDefinitionSchema'

export const FORM_PREVIEW_INCOMPLETE_TOOLTIP = 'Complete the required details for each form field to preview the form.'

export function isFormDefinitionReadyForPreview(definition: FormDefinition): boolean {
  const prepared = prepareFormDefinitionForCommit(definition)
  return safeParseFormDefinition(prepared).success
}
