import { SelectOption } from '@patternfly/react-core'
import type { ReactElement } from 'react'
import { useCallback, useMemo } from 'react'
import type { Control, ControllerFieldState, ControllerRenderProps, FieldPath, FieldValues } from 'react-hook-form'

import { SynFormField } from './SynFormField'
import { SynSelectFieldControlShell } from './synSelectFieldControlShell'
import type { SynSelectFieldOption } from './synSelectFieldTypes'

export type { SynSelectFieldOption } from './synSelectFieldTypes'

type SynSelectFieldControlProps<TFieldValues extends FieldValues, TName extends FieldPath<TFieldValues>> = {
  field: ControllerRenderProps<TFieldValues, TName>
  fieldState: ControllerFieldState
  resolvedFieldId: string
  label: string
  options: SynSelectFieldOption[]
  placeholder: string
  isDisabled?: boolean
}

function SynSelectFieldControl<TFieldValues extends FieldValues, TName extends FieldPath<TFieldValues>>({
  field,
  fieldState,
  resolvedFieldId,
  label,
  options,
  placeholder,
  isDisabled,
}: Readonly<SynSelectFieldControlProps<TFieldValues, TName>>) {
  const optionLabelByValue = useMemo(() => new Map(options.map((option) => [option.value, option.label])), [options])

  const selectedValue = field.value == null ? '' : String(field.value)
  const displayLabel = optionLabelByValue.get(selectedValue) ?? placeholder

  const handleSelect = useCallback(
    (_event: React.MouseEvent | undefined, value: string | number | undefined) => {
      if (value === undefined) return
      field.onChange(String(value))
    },
    [field]
  )

  return (
    <SynSelectFieldControlShell
      field={field}
      fieldState={fieldState}
      resolvedFieldId={resolvedFieldId}
      label={label}
      options={options}
      displayLabel={displayLabel}
      selected={selectedValue}
      onSelect={handleSelect}
      isDisabled={isDisabled}
      closeOnSelect
      shouldFocusToggleOnSelect
      renderOption={(option, isSelected) => (
        <SelectOption key={option.value} value={option.value} isSelected={isSelected} isDisabled={option.isDisabled}>
          {option.label}
        </SelectOption>
      )}
    />
  )
}

export type SynSelectFieldProps<
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
  /** Toggle text when no option is selected. Defaults to "Select an option". */
  placeholder?: string
  /** Disables the select. */
  isDisabled?: boolean
}

/**
 * A single-select dropdown bound to a react-hook-form field.
 *
 * Combines `SynFormField` + `SynSelect` with MenuToggle/SelectList wiring and
 * RHF bindings pre-wired. The visible FormGroup label is associated with the
 * toggle via `fieldId`; the toggle text reflects the placeholder or selection.
 *
 * @example
 * ```tsx
 * <SynSelectField
 *   name="projectId"
 *   control={control}
 *   label="Project"
 *   isRequired
 *   options={projects.map((p) => ({ value: p.id, label: p.name }))}
 * />
 * ```
 */
export function SynSelectField<
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
  placeholder = 'Select an option',
  isDisabled,
}: Readonly<SynSelectFieldProps<TFieldValues, TName>>) {
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
        <SynSelectFieldControl<TFieldValues, TName>
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
