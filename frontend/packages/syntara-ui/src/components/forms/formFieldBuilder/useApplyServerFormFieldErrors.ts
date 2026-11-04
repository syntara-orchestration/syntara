import type { FormDefinition } from '@syntara/contracts'
import { useEffect, useRef } from 'react'
import type { FieldPath, UseFormReturn } from 'react-hook-form'

import type { FormDefinitionFieldServerError } from './formDefinitionFieldServerError'

function toFieldPath(error: FormDefinitionFieldServerError): FieldPath<FormDefinition> {
  if (!error.subPath) {
    return `fields.${error.fieldIndex}` as FieldPath<FormDefinition>
  }
  return `fields.${error.fieldIndex}.${error.subPath}` as FieldPath<FormDefinition>
}

export function useApplyServerFormFieldErrors(
  form: UseFormReturn<FormDefinition>,
  serverFieldErrors?: ReadonlyArray<FormDefinitionFieldServerError>
) {
  const previousPathsRef = useRef<FieldPath<FormDefinition>[]>([])

  useEffect(() => {
    for (const path of previousPathsRef.current) {
      form.clearErrors(path)
    }
    previousPathsRef.current = []

    if (!serverFieldErrors?.length) {
      return
    }

    const paths: FieldPath<FormDefinition>[] = []
    for (const err of serverFieldErrors) {
      const path = toFieldPath(err)
      form.setError(path, { message: err.message })
      paths.push(path)
    }
    previousPathsRef.current = paths
  }, [form, serverFieldErrors])
}
