import yaml from 'js-yaml'
import type { UseFormGetValues, UseFormSetValue } from 'react-hook-form'

import type { AAPJobTemplateDetail } from '../../../hooks/useAAPBrowser'

import type { AAPJobTemplateFormData } from './aapJobTemplateSchema'

type SetValue = UseFormSetValue<AAPJobTemplateFormData>
type GetValues = UseFormGetValues<AAPJobTemplateFormData>

/** Sanitize array field to handle legacy single-value or invalid data */
export function sanitizeArrayField(value: unknown): number[] {
  if (Array.isArray(value)) {
    return value as number[]
  }
  if (typeof value === 'number') {
    return [value]
  }
  return []
}

/** Detect if a string contains a ${...} expression */
export function isExpression(value: string | undefined): boolean {
  return value?.includes('${') ?? false
}

function applyResourceDefaults(
  detail: AAPJobTemplateDetail,
  templateChanged: boolean,
  getValues: GetValues,
  setValue: SetValue
): void {
  if (detail.ask_inventory_on_launch && detail.default_inventory && (!getValues('inventory_name') || templateChanged)) {
    setValue('inventory_name', detail.default_inventory.name)
    setValue('inventory_id', detail.default_inventory.id)
  }

  if (
    detail.ask_execution_environment_on_launch &&
    detail.default_execution_environment &&
    (!getValues('execution_environment') || templateChanged)
  ) {
    setValue('execution_environment', detail.default_execution_environment.name)
    setValue('execution_environment_id', detail.default_execution_environment.id)
  }

  if (
    detail.ask_credential_on_launch &&
    detail.default_credentials?.length &&
    (!getValues('job_credentials')?.length || templateChanged)
  ) {
    setValue(
      'job_credentials',
      detail.default_credentials.map((c) => c.id)
    )
  }
}

function applyScalarDefaults(
  detail: AAPJobTemplateDetail,
  templateChanged: boolean,
  getValues: GetValues,
  setValue: SetValue
): void {
  const scalarFields: Array<{
    askFlag: keyof AAPJobTemplateDetail
    defaultKey: keyof AAPJobTemplateDetail
    formKey: keyof AAPJobTemplateFormData
    transform?: (value: unknown) => unknown
  }> = [
    { askFlag: 'ask_job_type_on_launch', defaultKey: 'job_type', formKey: 'job_type' },
    { askFlag: 'ask_verbosity_on_launch', defaultKey: 'verbosity', formKey: 'verbosity', transform: String },
    { askFlag: 'ask_forks_on_launch', defaultKey: 'forks', formKey: 'forks' },
    { askFlag: 'ask_limit_on_launch', defaultKey: 'limit', formKey: 'limit' },
    { askFlag: 'ask_tags_on_launch', defaultKey: 'job_tags', formKey: 'tags' },
    { askFlag: 'ask_skip_tags_on_launch', defaultKey: 'skip_tags', formKey: 'skip_tags' },
    { askFlag: 'ask_diff_mode_on_launch', defaultKey: 'diff_mode', formKey: 'diff_mode' },
    { askFlag: 'ask_job_slice_count_on_launch', defaultKey: 'job_slice_count', formKey: 'job_slice_count' },
  ]

  for (const { askFlag, defaultKey, formKey, transform } of scalarFields) {
    const askValue = detail[askFlag]
    const defaultValue = detail[defaultKey]
    const currentValue = getValues(formKey)

    // Treat undefined, null, and empty string as "not set", but preserve false and 0 as valid user selections
    const isEmpty = currentValue === undefined || currentValue === null || currentValue === ''

    if (askValue && defaultValue !== null && defaultValue !== undefined && (isEmpty || templateChanged)) {
      const transformedValue = transform ? transform(defaultValue) : defaultValue
      // eslint-disable-next-line @typescript-eslint/no-explicit-any, @typescript-eslint/no-unsafe-argument -- table-driven defaults require dynamic typing
      setValue(formKey, transformedValue as any)
    }
  }
}

function applyExtraVarsDefaults(
  detail: AAPJobTemplateDetail,
  templateChanged: boolean,
  getValues: GetValues,
  setValue: SetValue
): void {
  if (!detail.ask_variables_on_launch || !detail.extra_vars || (getValues('extra_vars') && !templateChanged)) return

  try {
    const parsed = yaml.load(detail.extra_vars)
    setValue('extra_vars', JSON.stringify(parsed, null, 2))
  } catch {
    setValue('extra_vars', detail.extra_vars)
  }
}

function applyLabelsDefaults(
  detail: AAPJobTemplateDetail,
  templateChanged: boolean,
  getValues: GetValues,
  setValue: SetValue
): void {
  if (!detail.ask_labels_on_launch) return

  if (detail.default_labels?.length && (!getValues('labels')?.length || templateChanged)) {
    setValue(
      'labels',
      detail.default_labels.map((l) => l.name)
    )
  } else if (templateChanged) {
    setValue('labels', [])
  }
}

/**
 * Apply default values from job template to form fields.
 * Only sets defaults if:
 * 1. The template allows prompting for that field (ask_*_on_launch flag)
 * 2. The user hasn't already selected a value OR the template changed
 */
export function applyDefaultValues(
  detail: AAPJobTemplateDetail,
  templateChanged: boolean,
  getValues: GetValues,
  setValue: SetValue
): void {
  applyResourceDefaults(detail, templateChanged, getValues, setValue)
  applyScalarDefaults(detail, templateChanged, getValues, setValue)
  applyExtraVarsDefaults(detail, templateChanged, getValues, setValue)
  applyLabelsDefaults(detail, templateChanged, getValues, setValue)
}
