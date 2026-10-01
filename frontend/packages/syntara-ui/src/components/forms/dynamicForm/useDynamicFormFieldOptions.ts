import type { FormField } from '@syntara/contracts'
import { useQuery } from '@tanstack/react-query'
import { useEffect, useMemo, useRef } from 'react'

import type { DynamicOptionsResolver, SynDynamicFormSelectOption } from '../SynDynamicForm.types'

import { normalizeDynamicOptionsResult } from './mapDynamicOptionsFromRecords'
import { resolveStaticOptions } from './resolveStaticOptions'
import { isOptionsFormField, type DynamicOptionsSource, type OptionsFormField } from './synDynamicFormFieldTypes'

type DynamicFormFieldOptionsState = {
  options: readonly SynDynamicFormSelectOption[]
  isLoading: boolean
  isError: boolean
  loadErrorMessage: string | null
}

function getDynamicExpression(field: OptionsFormField): string | null {
  if (field.options.source !== 'dynamic') {
    return null
  }
  return field.options.expression
}

function getStaticOptions(optionsField: OptionsFormField | null): readonly SynDynamicFormSelectOption[] {
  if (optionsField?.options.source !== 'static') {
    return []
  }
  return resolveStaticOptions(optionsField.options)
}

function buildDynamicOptionsQueryKey(parts: {
  valueName: string
  fieldType: OptionsFormField['type']
  expression: string
  labelKey?: string
  valueKey?: string
}): readonly (string | undefined)[] {
  return [
    'syn-dynamic-form-field-options',
    parts.valueName,
    parts.fieldType,
    'dynamic',
    parts.expression,
    parts.labelKey,
    parts.valueKey,
  ]
}

function getQueryLoadErrorMessage(error: unknown): string {
  return error instanceof Error ? error.message : 'Failed to load options.'
}

function missingResolverResult(): DynamicFormFieldOptionsState {
  return {
    options: [],
    isLoading: false,
    isError: true,
    loadErrorMessage: 'Dynamic options require a resolver.',
  }
}

function staticFieldResult(staticOptions: readonly SynDynamicFormSelectOption[]): DynamicFormFieldOptionsState {
  return { options: staticOptions, isLoading: false, isError: false, loadErrorMessage: null }
}

async function fetchDynamicOptions(
  optionsConfig: DynamicOptionsSource,
  optionsField: OptionsFormField,
  resolveDynamicOptions: DynamicOptionsResolver
): Promise<readonly SynDynamicFormSelectOption[]> {
  const raw = await resolveDynamicOptions(optionsConfig.expression, {
    ...optionsField,
    options: optionsConfig,
  })
  return normalizeDynamicOptionsResult(raw, optionsConfig)
}

export function useDynamicFormFieldOptions(
  field: FormField,
  resolveDynamicOptions?: DynamicOptionsResolver
): DynamicFormFieldOptionsState {
  const optionsField = isOptionsFormField(field) ? field : null
  const dynamicExpression = optionsField ? getDynamicExpression(optionsField) : null
  const staticOptions = getStaticOptions(optionsField)
  const dynamicOptionsConfig = optionsField?.options.source === 'dynamic' ? optionsField.options : null

  const valueName = optionsField?.value_name
  const fieldType = optionsField?.type
  const dynamicExpressionKey = dynamicOptionsConfig?.expression
  const dynamicLabelKey = dynamicOptionsConfig?.label_key
  const dynamicValueKey = dynamicOptionsConfig?.value_key

  const resolveDynamicOptionsRef = useRef(resolveDynamicOptions)
  useEffect(() => {
    resolveDynamicOptionsRef.current = resolveDynamicOptions
  }, [resolveDynamicOptions])

  const queryKey = useMemo(() => {
    if (!valueName || !fieldType || !dynamicExpressionKey) {
      return ['syn-dynamic-form-field-options', 'none']
    }
    return buildDynamicOptionsQueryKey({
      valueName,
      fieldType,
      expression: dynamicExpressionKey,
      labelKey: dynamicLabelKey ?? undefined,
      valueKey: dynamicValueKey ?? undefined,
    })
  }, [valueName, fieldType, dynamicExpressionKey, dynamicLabelKey, dynamicValueKey])

  const queryEnabled = Boolean(optionsField && dynamicExpression && resolveDynamicOptions)

  // Stable key parts only; resolver is read from a ref (callers should pass useCallback).
  // eslint-disable-next-line @tanstack/query/exhaustive-deps -- optionsField identity is encoded in queryKey
  const query = useQuery({
    queryKey,
    queryFn: () => {
      const resolve = resolveDynamicOptionsRef.current
      if (optionsField?.options.source !== 'dynamic' || !resolve) {
        return []
      }
      return fetchDynamicOptions(optionsField.options, optionsField, resolve)
    },
    enabled: queryEnabled,
    staleTime: 30_000,
  })

  if (!optionsField || !dynamicExpression) {
    return staticFieldResult(staticOptions)
  }

  if (!resolveDynamicOptions) {
    return missingResolverResult()
  }

  const loadErrorMessage = query.isError ? getQueryLoadErrorMessage(query.error) : null

  return {
    options: query.data ?? [],
    isLoading: query.isLoading,
    isError: query.isError,
    loadErrorMessage,
  }
}
