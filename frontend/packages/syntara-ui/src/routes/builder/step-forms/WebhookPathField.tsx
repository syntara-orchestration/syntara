import { FormGroup, FormHelperText, HelperText, HelperTextItem, StackItem, TextInput } from '@patternfly/react-core'
import type { ReactElement } from 'react'
import { Controller, useFormContext } from 'react-hook-form'

import type { TriggerFormData } from './triggerFormSchema'

type WebhookPathFieldProps = {
  /** Plain string label for the field. */
  label: string
  /** Optional PatternFly labelHelp popover. */
  labelHelp?: ReactElement
  /** Placeholder text for the input (e.g., "/jira-updates" or "/eda-events"). */
  placeholder: string
  /** Default helper text shown when there is no error. */
  helperText: string
  /** Validation error message (if any). */
  error?: string
  /** DOM id for the FormGroup and TextInput (defaults to "webhook-path"). */
  fieldId?: string
}

/**
 * Shared webhook path input field used by both webhook and EDA trigger forms.
 * Encapsulates the Controller + TextInput + FormHelperText pattern for the
 * `webhookPath` form field.
 */
export function WebhookPathField({
  label,
  labelHelp,
  placeholder,
  helperText,
  error,
  fieldId = 'webhook-path',
}: Readonly<WebhookPathFieldProps>) {
  const { control } = useFormContext<TriggerFormData>()

  return (
    <StackItem>
      <FormGroup label={label} labelHelp={labelHelp} fieldId={fieldId} isRequired>
        <Controller
          control={control}
          name="webhookPath"
          render={({ field }) => (
            <TextInput
              id={fieldId}
              aria-label="Webhook path"
              placeholder={placeholder}
              validated={error ? 'error' : 'default'}
              value={field.value ?? ''}
              onChange={(_event, value) => field.onChange(value)}
              onBlur={field.onBlur}
            />
          )}
        />
        <FormHelperText>
          <HelperText>
            <HelperTextItem variant={error ? 'error' : 'default'}>{error ?? helperText}</HelperTextItem>
          </HelperText>
        </FormHelperText>
      </FormGroup>
    </StackItem>
  )
}
