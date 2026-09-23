import type { ReactElement } from 'react'
import type { Control, ControllerFieldState, ControllerRenderProps, FieldPath, FieldValues } from 'react-hook-form'

import { EXPRESSION_FIELD_PLACEHOLDER } from '../expressions/expressionFieldDrag'

import { ExpressionFieldInput } from './ExpressionFieldInput'
import { SynFormField } from './SynFormField'

type SynExpressionFieldControlProps<TFieldValues extends FieldValues, TName extends FieldPath<TFieldValues>> = {
  field: ControllerRenderProps<TFieldValues, TName>
  fieldState: ControllerFieldState
  resolvedFieldId: string
  placeholder: string
  hint?: string
  isDisabled?: boolean
}

function SynExpressionFieldControl<TFieldValues extends FieldValues, TName extends FieldPath<TFieldValues>>({
  field,
  fieldState,
  resolvedFieldId,
  placeholder,
  hint,
  isDisabled,
}: Readonly<SynExpressionFieldControlProps<TFieldValues, TName>>) {
  const value = typeof field.value === 'string' ? field.value : ''

  return (
    <ExpressionFieldInput
      id={resolvedFieldId}
      value={value}
      onChange={field.onChange}
      onBlur={field.onBlur}
      name={field.name}
      placeholder={placeholder}
      isDisabled={isDisabled}
      externalError={fieldState.error?.message}
      hint={hint}
    />
  )
}

export type SynExpressionFieldProps<
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
  /** Label text rendered above the expression input. */
  label: string
  /**
   * HTML `id` used as `FormGroup.fieldId` and on the text input.
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
  /** Placeholder text shown inside the input when empty. */
  placeholder?: string
  /** Disables the input. */
  isDisabled?: boolean
}

/**
 * An expression text input bound to a react-hook-form string field.
 *
 * Combines `SynFormField` + `ExpressionFieldInput` with drag-and-drop support
 * for builder field/context tokens and inline `${...}` syntax validation.
 *
 * @example
 * ```tsx
 * <SynExpressionField
 *   name="condition"
 *   control={control}
 *   label="Condition"
 *   isRequired
 * />
 * ```
 */
export function SynExpressionField<
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
  placeholder = EXPRESSION_FIELD_PLACEHOLDER,
  isDisabled,
}: Readonly<SynExpressionFieldProps<TFieldValues, TName>>) {
  const resolvedFieldId = fieldId ?? name

  return (
    <SynFormField
      name={name}
      control={control}
      label={label}
      fieldId={resolvedFieldId}
      isRequired={isRequired}
      labelHelp={labelHelp}
      hideFooter
    >
      {({ field, fieldState }) => (
        <SynExpressionFieldControl<TFieldValues, TName>
          field={field}
          fieldState={fieldState}
          resolvedFieldId={resolvedFieldId}
          placeholder={placeholder}
          hint={hint}
          isDisabled={isDisabled}
        />
      )}
    </SynFormField>
  )
}
