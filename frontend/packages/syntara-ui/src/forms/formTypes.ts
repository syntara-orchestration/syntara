import type { FormField } from '@syntara/contracts'

export type FormFieldByType<T extends FormField['type']> = Extract<FormField, { type: T }>

export type StaticOptionsSource = Extract<FormField, { options: { source: 'static' } }>['options']
export type ResolvedOptionsSource = Extract<FormField, { options: { source: 'dynamic_resolved' } }>['options']
export type DynamicOptionsSource = Extract<FormField, { options: { source: 'dynamic' } }>['options']

/** Raw submitted values keyed by `value_name` before coercion. */
export type FormSubmissionInput = Record<string, unknown>

/**
 * Coerced value of a date field: exactly the components the field collects.
 *
 * Always an object, even for a date-only field, so that enabling a timezone
 * later cannot silently change the shape downstream consumers read.
 */
export type DateSubmissionValue = {
  date?: string
  time?: string
  timezone?: string
}

/** Coerced submission payload ready for API / workflow namespace. */
export type FormSubmissionData = Record<
  string,
  string | number | boolean | (string | number | boolean)[] | DateSubmissionValue
>
