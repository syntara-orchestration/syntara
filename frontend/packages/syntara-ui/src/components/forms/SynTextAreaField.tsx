import { TextArea } from '@patternfly/react-core'
import type { ReactElement } from 'react'
import type { Control, FieldPath, FieldValues } from 'react-hook-form'

import { SynFormField } from './SynFormField'

export type SynTextAreaFieldProps<
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
  /** Label text rendered above the textarea. */
  label: string
  /**
   * HTML `id` used as `FormGroup.fieldId` and on the `TextArea`.
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
   * Static helper text shown below the textarea when there is no validation error.
   * Replaced by the error message when a validation error is present.
   */
  hint?: string
  /** Placeholder text shown inside the textarea when empty. */
  placeholder?: string
  /** Number of visible text rows. */
  rows?: number
  /** Disables the textarea. */
  isDisabled?: boolean
}

/**
 * A multi-line text area bound to a react-hook-form field.
 *
 * Combines `SynFormField` + PatternFly `TextArea` with all RHF bindings
 * (`value`, `onChange`, `onBlur`, `name`, `validated`) pre-wired.
 *
 * @example
 * ```tsx
 * <SynTextAreaField
 *   name="description"
 *   control={control}
 *   label="Description"
 *   placeholder="Enter description"
 *   rows={3}
 * />
 * ```
 */
export function SynTextAreaField<
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
  rows,
  isDisabled,
}: Readonly<SynTextAreaFieldProps<TFieldValues, TName>>) {
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
        <TextArea
          id={resolvedFieldId}
          placeholder={placeholder}
          validated={fieldState.error ? 'error' : 'default'}
          value={field.value ?? ''}
          onChange={field.onChange}
          onBlur={field.onBlur}
          name={field.name}
          rows={rows}
          isDisabled={isDisabled}
        />
      )}
    </SynFormField>
  )
}
