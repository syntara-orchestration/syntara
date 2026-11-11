import type { FormDefinition } from '@syntara/contracts'
import { useMemo } from 'react'

import type { FormDefinitionFieldServerError } from '../../../components/forms/formFieldBuilder/formDefinitionFieldServerError'
import { mapFormFieldValidationErrorsToServerErrors } from '../../../components/forms/formFieldBuilder/mapFormFieldValidationErrorsToServerErrors'
import { prepareFormDefinitionForCommit, safeParseFormDefinition } from '../../../forms'
import { partitionFormTriggerServerValidationErrors } from '../utils/partitionFormTriggerServerValidationErrors'

type ServerValidationError = Readonly<{ fieldPath?: string | null; message: string }>

function mergeFormDefinitionFieldServerErrors(
  fromServer: ReadonlyArray<FormDefinitionFieldServerError>,
  supplemental: ReadonlyArray<FormDefinitionFieldServerError>
): FormDefinitionFieldServerError[] {
  if (supplemental.length === 0) {
    return [...fromServer]
  }
  const keys = new Set(fromServer.map((error) => `${error.fieldIndex}:${error.subPath}`))
  const merged = [...fromServer]
  for (const error of supplemental) {
    const key = `${error.fieldIndex}:${error.subPath}`
    if (keys.has(key)) {
      continue
    }
    merged.push(error)
    keys.add(key)
  }
  return merged
}

/**
 * Inline field errors for draft {@link SynFormFieldBuilder}: parsed API field_paths plus local
 * schema findings while verify/save banner errors are still active (banner copy often has no field_path).
 *
 * Callers should compute effective banner errors once with {@link useEffectiveFormDefinitionServerValidationErrors}.
 */
export function useFormDefinitionFieldServerErrors(
  formDefinition: FormDefinition | undefined,
  effectiveServerValidationErrors: ReadonlyArray<ServerValidationError> | undefined,
  readPreparedDefinition?: () => FormDefinition | undefined
): FormDefinitionFieldServerError[] {
  return useMemo(() => {
    const fromServer = partitionFormTriggerServerValidationErrors(effectiveServerValidationErrors).formFieldErrors
    if (!effectiveServerValidationErrors?.length) {
      return fromServer
    }

    const candidate = readPreparedDefinition?.() ?? formDefinition
    const parsed = safeParseFormDefinition(prepareFormDefinitionForCommit(candidate ?? { fields: [] }))
    if (parsed.success) {
      return fromServer
    }

    const fromLocal = mapFormFieldValidationErrorsToServerErrors(parsed.errors)
    return mergeFormDefinitionFieldServerErrors(fromServer, fromLocal)
  }, [effectiveServerValidationErrors, formDefinition, readPreparedDefinition])
}
