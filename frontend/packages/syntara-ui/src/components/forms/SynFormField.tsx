import { FormGroup } from '@patternfly/react-core'
import type { ReactElement, ReactNode } from 'react'
import type { Control, ControllerFieldState, ControllerRenderProps, FieldPath, FieldValues } from 'react-hook-form'
import { useController } from 'react-hook-form'

import { FormFieldError, FormFieldHintOrError } from '../FormFieldError'

export type SynFormFieldProps<
  TFieldValues extends FieldValues = FieldValues,
  TName extends FieldPath<TFieldValues> = FieldPath<TFieldValues>,
> = {
  /** RHF field name — must match a key in the form schema. */
  name: TName
  /**
   * RHF `control` object from `useForm` or `useSynForm`. When omitted the
   * field reads from the nearest `FormProvider` context (self-registering mode).
   */
  control?: Control<TFieldValues>
  /** Label text rendered above the field. */
  label: string
  /**
   * HTML `id` used as `FormGroup.fieldId` and forwarded to the inner element
   * via the render-prop. Defaults to the `name` prop.
   */
  fieldId?: string
  /** Marks the field as required with a visual indicator. */
  isRequired?: boolean
  /**
   * Popover content shown next to the label via PatternFly `FormGroup.labelHelp`.
   * Must be a `ReactElement` (e.g. a `FieldHelpPopover`) — PF6 does not accept
   * plain nodes.
   */
  labelHelp?: ReactElement
  /**
   * Static helper text shown below the field when there is no validation error.
   * When an error is present the error message replaces this hint.
   */
  hint?: string
  /**
   * Render prop receiving the RHF field and fieldState. Use these to bind the
   * inner input (`value`, `onChange`, `onBlur`, `name`) and set `validated`.
   *
   * @example
   * ```tsx
   * <SynFormField name="username" control={control} label="Username">
   *   {({ field, fieldState }) => (
   *     <TextInput
   *       id="username"
   *       validated={fieldState.error ? 'error' : 'default'}
   *       value={field.value ?? ''}
   *       onChange={field.onChange}
   *       onBlur={field.onBlur}
   *       name={field.name}
   *     />
   *   )}
   * </SynFormField>
   * ```
   */
  children: (renderProps: {
    field: ControllerRenderProps<TFieldValues, TName>
    fieldState: ControllerFieldState
  }) => ReactNode
}

/**
 * Binds a PatternFly `FormGroup` to a react-hook-form field via `useController`.
 * Renders the label, optional help popover, the field via render prop, and
 * validation error (or hint) below the field.
 *
 * Prefer the specialised wrappers (`SynTextField`, `SynTextAreaField`) for
 * standard text inputs. Use `SynFormField` directly for custom controls
 * (selects, checkboxes, date pickers, etc.).
 */
export function SynFormField<
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
  children,
}: Readonly<SynFormFieldProps<TFieldValues, TName>>) {
  const { field, fieldState } = useController({ name, control })
  const resolvedFieldId = fieldId ?? name

  return (
    <FormGroup label={label} fieldId={resolvedFieldId} isRequired={isRequired} labelHelp={labelHelp}>
      {children({ field, fieldState })}
      {hint ? (
        <FormFieldHintOrError hint={hint} error={fieldState.error} />
      ) : (
        <FormFieldError error={fieldState.error} />
      )}
    </FormGroup>
  )
}
