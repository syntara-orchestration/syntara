import { StackItem } from '@patternfly/react-core'
import type { ReactElement } from 'react'

import { SynTextField } from '../../../components/forms/SynTextField'

type WebhookPathFieldProps = {
  /** Plain string label for the field. */
  label: string
  /** Optional PatternFly labelHelp popover. */
  labelHelp?: ReactElement
  /** Placeholder text for the input (e.g., "/jira-updates" or "/eda-events"). */
  placeholder: string
  /** Default helper text shown when there is no error. */
  helperText: string
  /** DOM id for the FormGroup and TextInput (defaults to "webhook-path"). */
  fieldId?: string
}

/**
 * Shared webhook path input field used by both webhook and EDA trigger forms.
 */
export function WebhookPathField({
  label,
  labelHelp,
  placeholder,
  helperText,
  fieldId = 'webhook-path',
}: Readonly<WebhookPathFieldProps>) {
  return (
    <StackItem>
      <SynTextField
        name="webhookPath"
        label={label}
        ariaLabel="Webhook path"
        labelHelp={labelHelp}
        fieldId={fieldId}
        isRequired
        placeholder={placeholder}
        hint={helperText}
      />
    </StackItem>
  )
}
