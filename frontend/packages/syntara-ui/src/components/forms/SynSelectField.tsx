import { SelectList, SelectOption } from '@patternfly/react-core'
import type { MenuToggleElement } from '@patternfly/react-core'
import type { ReactElement, Ref } from 'react'
import { useCallback, useMemo, useState } from 'react'
import type { Control, ControllerFieldState, ControllerRenderProps, FieldPath, FieldValues } from 'react-hook-form'

import { SynSelect } from '../SynSelect'

import { SynFormField } from './SynFormField'
import { SynSelectFieldToggle, type SynSelectFieldToggleState } from './synSelectFieldToggle'
import type { SynSelectFieldOption } from './synSelectFieldTypes'

export type { SynSelectFieldOption } from './synSelectFieldTypes'

function renderSynSelectFieldToggle(toggleRef: Ref<MenuToggleElement>, state: SynSelectFieldToggleState) {
  return <SynSelectFieldToggle toggleRef={toggleRef} {...state} />
}

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
  const [isOpen, setIsOpen] = useState(false)

  const optionLabelByValue = useMemo(() => new Map(options.map((option) => [option.value, option.label])), [options])

  const selectedValue = field.value == null ? '' : String(field.value)
  const displayLabel = optionLabelByValue.get(selectedValue) ?? placeholder
  const hasError = Boolean(fieldState.error)

  const handleToggle = useCallback(() => {
    setIsOpen((open) => !open)
  }, [])

  const handleSelect = useCallback(
    (_event: React.MouseEvent | undefined, value: string | number | undefined) => {
      if (value === undefined) return
      field.onChange(String(value))
      setIsOpen(false)
    },
    [field]
  )

  const toggleState = useMemo<SynSelectFieldToggleState>(
    () => ({
      displayLabel,
      isOpen,
      onToggle: handleToggle,
      onBlur: field.onBlur,
      isDisabled,
      hasError,
    }),
    [displayLabel, field.onBlur, handleToggle, hasError, isDisabled, isOpen]
  )

  const renderToggle = useCallback(
    (toggleRef: Ref<MenuToggleElement>) => renderSynSelectFieldToggle(toggleRef, toggleState),
    [toggleState]
  )

  return (
    <SynSelect
      id={resolvedFieldId}
      aria-label={label}
      isOpen={isOpen}
      selected={selectedValue}
      onSelect={handleSelect}
      onOpenChange={setIsOpen}
      toggle={renderToggle}
      shouldFocusToggleOnSelect
    >
      <SelectList aria-label={`${label} options`}>
        {options.map((option) => (
          <SelectOption
            key={option.value}
            value={option.value}
            isSelected={option.value === selectedValue}
            isDisabled={option.isDisabled}
          >
            {option.label}
          </SelectOption>
        ))}
      </SelectList>
    </SynSelect>
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
 * RHF bindings pre-wired.
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
