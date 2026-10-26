import type { FormDefinition } from '@syntara/contracts'

import { prepareFormDefinitionForCommit, safeParseFormDefinition } from '../../../forms'

/** Parse and normalize `form_definition` from stored activity/trigger parameters. */
export function readStoredFormDefinition(rawParameters: unknown): FormDefinition | undefined {
  if (typeof rawParameters !== 'object' || rawParameters === null) {
    return undefined
  }
  const raw = (rawParameters as { form_definition?: unknown }).form_definition
  if (typeof raw !== 'object' || raw === null || !('fields' in raw)) {
    return undefined
  }
  const prepared = prepareFormDefinitionForCommit(raw as FormDefinition)
  const parsed = safeParseFormDefinition(prepared)
  return parsed.success ? parsed.data : undefined
}
