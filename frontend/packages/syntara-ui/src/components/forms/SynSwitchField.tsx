import { Switch } from '@patternfly/react-core'
import type { Control, FieldPath, FieldValues } from 'react-hook-form'

import { SynFormField } from './SynFormField'

export type SynSwitchFieldProps<
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
  /** Label text rendered on the switch control. */
  label: string
  /**
   * HTML `id` used as `FormGroup.fieldId` and on the switch.
   * Defaults to the `name` prop.
   */
  fieldId?: string
  /**
   * Static helper text shown below the field when there is no validation error.
   * Replaced by the error message when a validation error is present.
   */
  hint?: string
  /** Disables the switch. */
  isDisabled?: boolean
}

/**
 * A boolean switch bound to a react-hook-form field.
 *
 * Combines `SynFormField` + PatternFly `Switch` with RHF bindings pre-wired.
 * The visible label is rendered on the switch; the form group provides field
 * metadata and validation messaging. Use `hint` for inline help — `labelHelp`
 * is omitted because the group label is hidden.
 *
 * @example
 * ```tsx
 * <SynSwitchField
 *   name="enabled"
 *   control={control}
 *   label="Enable feature"
 *   hint="Turn on to allow access for all authenticated users."
 * />
 * ```
 */
export function SynSwitchField<
  TFieldValues extends FieldValues = FieldValues,
  TName extends FieldPath<TFieldValues> = FieldPath<TFieldValues>,
>({ name, control, label, fieldId, hint, isDisabled }: Readonly<SynSwitchFieldProps<TFieldValues, TName>>) {
  const resolvedFieldId = fieldId ?? name

  return (
    <SynFormField name={name} control={control} label={label} fieldId={resolvedFieldId} hideFormGroupLabel hint={hint}>
      {({ field }) => (
        <Switch
          id={resolvedFieldId}
          label={label}
          hasCheckIcon
          isChecked={Boolean(field.value)}
          onChange={(_event, checked) => field.onChange(checked)}
          onBlur={field.onBlur}
          name={field.name}
          isDisabled={isDisabled}
        />
      )}
    </SynFormField>
  )
}
