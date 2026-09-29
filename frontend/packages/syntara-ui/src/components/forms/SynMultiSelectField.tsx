import { SelectOption } from '@patternfly/react-core'
import type { ReactElement } from 'react'
import { useCallback } from 'react'
import type { Control, ControllerFieldState, ControllerRenderProps, FieldPath, FieldValues } from 'react-hook-form'

import { SynFormField } from './SynFormField'
import { SynSelectFieldControlShell } from './synSelectFieldControlShell'
import type { SynSelectFieldOption } from './synSelectFieldTypes'

export type { SynSelectFieldOption } from './synSelectFieldTypes'

function normalizeSelectedValues(value: unknown): string[] {
  if (!Array.isArray(value)) return []
  return value.map(String)
}

function formatSelectedLabels(selectedValues: string[], options: SynSelectFieldOption[], placeholder: string): string {
  if (selectedValues.length === 0) return placeholder
  const labelByValue = new Map(options.map((option) => [option.value, option.label]))
  const labels = selectedValues.map((value) => labelByValue.get(value) ?? value)
  if (labels.length <= 2) return labels.join(', ')
  return `${labels.length} selected`
}

type SynMultiSelectFieldControlProps<TFieldValues extends FieldValues, TName extends FieldPath<TFieldValues>> = {
  field: ControllerRenderProps<TFieldValues, TName>
  fieldState: ControllerFieldState
  resolvedFieldId: string
  label: string
  options: SynSelectFieldOption[]
  placeholder: string
  isDisabled?: boolean
}

function SynMultiSelectFieldControl<TFieldValues extends FieldValues, TName extends FieldPath<TFieldValues>>({
  field,
  fieldState,
  resolvedFieldId,
  label,
  options,
  placeholder,
  isDisabled,
}: Readonly<SynMultiSelectFieldControlProps<TFieldValues, TName>>) {
  const selectedValues = normalizeSelectedValues(field.value)
  const displayLabel = formatSelectedLabels(selectedValues, options, placeholder)

  const handleSelect = useCallback(
    (_event: React.MouseEvent | undefined, value: string | number | undefined) => {
      if (value === undefined) return
      const stringValue = String(value)
      const nextValues = selectedValues.includes(stringValue)
        ? selectedValues.filter((item) => item !== stringValue)
        : [...selectedValues, stringValue]
      field.onChange(nextValues)
    },
    [field, selectedValues]
  )

  return (
    <SynSelectFieldControlShell
      field={field}
      fieldState={fieldState}
      resolvedFieldId={resolvedFieldId}
      label={label}
      options={options}
      displayLabel={displayLabel}
      selected={selectedValues}
      onSelect={handleSelect}
      isDisabled={isDisabled}
      renderOption={(option, isSelected) => (
        <SelectOption
          key={option.value}
          value={option.value}
          hasCheckbox
          isSelected={isSelected}
          isDisabled={option.isDisabled}
        >
          {option.label}
        </SelectOption>
      )}
    />
  )
}

export type SynMultiSelectFieldProps<
  TFieldValues extends FieldValues = FieldValues,
  TName extends FieldPath<TFieldValues> = FieldPath<TFieldValues>,
> = {
  /** RHF field name — must match a key in the form schema. */
  name: TName
  /**
   * RHF `control` object from `useForm` or `useSynForm`. When omitted the
   * field reads from the nearest `FormProvider` context.
   */
  control?: Control<TFieldValues>
  /** Label text rendered above the select. */
  label: string
  /**
   * HTML `id` used as `FormGroup.fieldId` and on the select toggle.
   * Defaults to the `name` prop.
   */
  fieldId?: string
  /** Marks the field as required with a visual indicator. */
  isRequired?: boolean
  /**
   * Popover content shown next to the label via PatternFly `FormGroup.labelHelp`.
   * Must be a `ReactElement` — PF6 does not accept plain nodes.
   */
  labelHelp?: ReactElement
  /**
   * Static helper text shown below the field when there is no validation error.
   * Replaced by the error message when a validation error is present.
   */
  hint?: string
  /** Available options for selection. */
  options: SynSelectFieldOption[]
  /** Toggle text when no options are selected. Defaults to "Select options". */
  placeholder?: string
  /** Disables the select. */
  isDisabled?: boolean
}

/**
 * A multi-select dropdown bound to a react-hook-form string-array field.
 *
 * Combines `SynFormField` + `SynSelect` with checkbox options and RHF bindings
 * pre-wired. The menu stays open after each selection so users can pick multiple
 * values without reopening the list.
 *
 * @example
 * ```tsx
 * <SynMultiSelectField
 *   name="groupNames"
 *   control={control}
 *   label="Groups"
 *   options={groups.map((g) => ({ value: g.name, label: g.name }))}
 * />
 * ```
 */
export function SynMultiSelectField<
  TFieldValues extends FieldValues = FieldValues,
  TName extends FieldPath<TFieldValues> = FieldPath<TFieldValues>,
>({
  name,
  control,
  label,
  fieldId,
  isRequired,
  labelHelp,
  hint,
  options,
  placeholder = 'Select options',
  isDisabled,
}: Readonly<SynMultiSelectFieldProps<TFieldValues, TName>>) {
  const resolvedFieldId = fieldId ?? name

  return (
    <SynFormField
      name={name}
      control={control}
      label={label}
      fieldId={resolvedFieldId}
      isRequired={isRequired}
      labelHelp={labelHelp}
      hint={hint}
    >
      {({ field, fieldState }) => (
        <SynMultiSelectFieldControl<TFieldValues, TName>
          field={field}
          fieldState={fieldState}
          resolvedFieldId={resolvedFieldId}
          label={label}
          options={options}
          placeholder={placeholder}
          isDisabled={isDisabled}
        />
      )}
    </SynFormField>
  )
}
