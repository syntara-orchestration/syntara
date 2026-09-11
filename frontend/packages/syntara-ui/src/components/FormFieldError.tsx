import { FormHelperText, HelperText, HelperTextItem } from '@patternfly/react-core'
import { RhUiErrorIcon } from '@patternfly/react-icons'
import type { FieldError } from 'react-hook-form'

type FormFieldErrorProps = Readonly<{
  /** Error message text. Takes precedence over `error` when both are provided. */
  message?: string
  /** react-hook-form field error — `message` is read from `error.message`. */
  error?: FieldError
}>

/** Displays a validation error message below a form field. */
export function FormFieldError({ message, error }: FormFieldErrorProps) {
  const resolvedMessage = message ?? error?.message
  if (!resolvedMessage) return null
  return (
    <FormHelperText>
      <HelperText>
        <HelperTextItem icon={<RhUiErrorIcon />} variant="error">
          {resolvedMessage}
        </HelperTextItem>
      </HelperText>
    </FormHelperText>
  )
}

type FormFieldHintOrErrorProps = Readonly<{
  /** Static helper text shown when there is no validation error. */
  hint: string
  /** react-hook-form field error — replaces the hint when present. */
  error?: FieldError
}>

/**
 * Shows a hint below a field when valid, or an error message (with icon) when invalid.
 * Use for fields where a persistent hint should be replaced by the validation error.
 */
export function FormFieldHintOrError({ error, hint }: FormFieldHintOrErrorProps) {
  if (error) {
    return <FormFieldError error={error} />
  }
  return (
    <FormHelperText>
      <HelperText>
        <HelperTextItem>{hint}</HelperTextItem>
      </HelperText>
    </FormHelperText>
  )
}

export function FormFieldWarning({ message }: Readonly<{ message?: string }>) {
  if (!message) return null
  return (
    <FormHelperText>
      <HelperText>
        <HelperTextItem variant="warning">{message}</HelperTextItem>
      </HelperText>
    </FormHelperText>
  )
}
