import type { FormField } from '@syntara/contracts'

export type FormFieldByType<T extends FormField['type']> = Extract<FormField, { type: T }>

export type StaticOptionsSource = Extract<FormField, { options: { source: 'static' } }>['options']
export type DynamicOptionsSource = Extract<FormField, { options: { source: 'dynamic' } }>['options']

/** Raw submitted values keyed by `value_name` before coercion. */
export type FormSubmissionInput = Record<string, unknown>

/** Coerced submission payload ready for API / workflow namespace. */
export type FormSubmissionData = Record<string, string | number | boolean | (string | number | boolean)[]>
