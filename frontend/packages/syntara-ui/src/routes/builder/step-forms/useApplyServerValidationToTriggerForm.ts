import { useEffect, useRef } from 'react'
import type { UseFormReturn } from 'react-hook-form'

import { partitionFormTriggerServerValidationErrors } from '../utils/partitionFormTriggerServerValidationErrors'

import type { TriggerFormData } from './triggerFormSchema'

export function useApplyServerValidationToTriggerForm(
  form: UseFormReturn<TriggerFormData>,
  serverValidationErrors?: ReadonlyArray<{ fieldPath?: string | null; message: string }>
) {
  const previousFieldsRef = useRef<Array<keyof TriggerFormData>>([])

  useEffect(() => {
    for (const field of previousFieldsRef.current) {
      form.clearErrors(field)
    }
    previousFieldsRef.current = []

    if (!serverValidationErrors?.length) {
      return
    }

    const { triggerFieldErrors } = partitionFormTriggerServerValidationErrors(serverValidationErrors)
    for (const err of triggerFieldErrors) {
      form.setError(err.field, { message: err.message })
      previousFieldsRef.current.push(err.field)
    }
  }, [form, serverValidationErrors])
}
