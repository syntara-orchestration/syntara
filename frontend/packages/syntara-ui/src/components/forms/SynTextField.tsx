import { TextInput } from '@patternfly/react-core'
import type { ReactElement } from 'react'
import type { Control, FieldPath, FieldValues } from 'react-hook-form'

import { SynFormField } from './SynFormField'

export type SynTextFieldProps<
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
  /** Label text rendered above the input. */
  label: string
  /**
   * HTML `id` used as `FormGroup.fieldId` and on the `TextInput`.
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
   * Static helper text shown below the input when there is no validation error.
   * Replaced by the error message when a validation error is present.
   */
  hint?: string
  /** Placeholder text shown inside the input when empty. */
  placeholder?: string
  /** Disables the input. */
  isDisabled?: boolean
  /** Input type. Defaults to `'text'`. */
  type?: 'text' | 'email' | 'password' | 'search' | 'tel' | 'url' | 'number'
}

/**
 * A single-line text input bound to a react-hook-form field.
 *
 * Combines `SynFormField` + PatternFly `TextInput` with all RHF bindings
 * (`value`, `onChange`, `onBlur`, `name`, `validated`) pre-wired.
 *
 * @example
 * ```tsx
 * <SynTextField
 *   name="name"
 *   control={control}
 *   label="Group name"
 *   isRequired
 *   placeholder="Enter group name"
 *   labelHelp={groupHelp.name}
 * />
 * ```
 */
export function SynTextField<
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
  placeholder,
  isDisabled,
  type = 'text',
}: Readonly<SynTextFieldProps<TFieldValues, TName>>) {
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
        <TextInput
          id={resolvedFieldId}
          type={type}
          placeholder={placeholder}
          validated={fieldState.error ? 'error' : 'default'}
          value={field.value ?? ''}
          onChange={field.onChange}
          onBlur={field.onBlur}
          name={field.name}
          isDisabled={isDisabled}
        />
      )}
    </SynFormField>
  )
}
