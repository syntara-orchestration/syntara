import type { FormDefinition } from '@syntara/contracts'

import type { FormFieldValidationError, FormSubmissionData, FormSubmissionInput } from '../../forms'

import type { DynamicOptionsFormField } from './dynamicForm/synDynamicFormFieldTypes'

/** Normalized select option for dropdown and multi-select fields. */
export type SynDynamicFormSelectOption = {
  label: string
  value: string | number | boolean
}

/**
 * Result from {@link DynamicOptionsResolver}: either pre-built options, or raw records
 * from evaluating `field.options.expression` (mapped with `label_key` / `value_key`).
 */
export type DynamicOptionsResolverResult = readonly SynDynamicFormSelectOption[] | readonly unknown[]

/**
 * Resolves dynamic dropdown options (TanStack Query `queryFn`).
 *
 * The `expression` is the schema's template reference (e.g. `${nodes.step.output.items}`).
 * Execution surfaces evaluate that expression, then either:
 *
 * - return {@link SynDynamicFormSelectOption}[] directly, or
 * - return an array of objects and rely on `field.options.label_key` / `value_key`
 *   (see {@link mapDynamicOptionsFromRecords}).
 *
 * File upload fields are not supported by this resolver yet.
 */
export type DynamicOptionsResolver = (
  expression: string,
  field: DynamicOptionsFormField
) => Promise<DynamicOptionsResolverResult>

export type SynDynamicFormProps = {
  definition: FormDefinition
  /** Copy shown above the fields (e.g. form prompt message). */
  description?: string | null
  /** Merged on top of schema defaults. */
  initialValues?: FormSubmissionInput
  isDisabled?: boolean
  isLoading?: boolean
  /**
   * Required when the definition includes dynamic option sources.
   * Pass a stable `useCallback` reference to avoid unnecessary query refetches.
   */
  resolveDynamicOptions?: DynamicOptionsResolver
  onSubmit: (data: FormSubmissionData) => void | Promise<void>
  onValidationError?: (errors: readonly FormFieldValidationError[]) => void
  submitLabel?: string
  /** Disables inputs and hides the submit button. */
  isReadOnly?: boolean
  hideSubmitButton?: boolean
  id?: string
  'data-testid'?: string
}
