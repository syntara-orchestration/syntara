import type { FormDefinition } from '@syntara/contracts'
import { useMemo } from 'react'

import { createEmptyFormDefinition } from '../../../components/forms/formFieldBuilder/createDefaultField'
import { isStoredFormDefinitionValid } from '../utils/clearNodeValidationErrors'

type ServerValidationError = Readonly<{ fieldPath?: string | null; message: string }>

type UseEffectiveFormDefinitionServerValidationErrorsOptions = Readonly<{
  /** When false, pass server errors through (non form-definition nodes). Default true. */
  applyFormDefinitionValidityCheck?: boolean
  /** Prefer the field builder's prepared snapshot when checking validity (matches Update / flush). */
  readPreparedDefinition?: () => FormDefinition | undefined
}>

function definitionForValidityCheck(
  formDefinition: FormDefinition | undefined,
  readPreparedDefinition?: () => FormDefinition | undefined
): FormDefinition {
  return readPreparedDefinition?.() ?? formDefinition ?? createEmptyFormDefinition()
}

/** Drop stale verify findings on the builder once the edited definition passes local validation. */
export function useEffectiveFormDefinitionServerValidationErrors(
  formDefinition: FormDefinition | undefined,
  serverValidationErrors?: ReadonlyArray<ServerValidationError>,
  options?: UseEffectiveFormDefinitionServerValidationErrorsOptions
): ReadonlyArray<ServerValidationError> | undefined {
  const readPreparedDefinition = options?.readPreparedDefinition
  const applyFormDefinitionValidityCheck = options?.applyFormDefinitionValidityCheck

  return useMemo(() => {
    if (!serverValidationErrors?.length) {
      return undefined
    }
    if (applyFormDefinitionValidityCheck === false) {
      return serverValidationErrors
    }
    const candidate = definitionForValidityCheck(formDefinition, readPreparedDefinition)
    if (isStoredFormDefinitionValid(candidate)) {
      return undefined
    }
    return serverValidationErrors
  }, [applyFormDefinitionValidityCheck, formDefinition, readPreparedDefinition, serverValidationErrors])
}
