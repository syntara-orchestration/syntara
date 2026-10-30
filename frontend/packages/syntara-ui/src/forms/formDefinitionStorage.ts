import type { FormDefinition } from '@syntara/contracts'

import { prepareFormDefinitionForCommit } from './dateFieldUtils'
import { safeParseFormDefinition } from './formDefinitionSchema'

/**
 * Normalize a form definition for persistence in workflow storage.
 * Uses strict parsing when valid; otherwise keeps the prepared draft so save is not blocked in the builder.
 */
export function serializeFormDefinitionForStorage(input: FormDefinition): FormDefinition {
  const prepared = prepareFormDefinitionForCommit(input)
  const parsed = safeParseFormDefinition(prepared)
  return parsed.success ? parsed.data : prepared
}
