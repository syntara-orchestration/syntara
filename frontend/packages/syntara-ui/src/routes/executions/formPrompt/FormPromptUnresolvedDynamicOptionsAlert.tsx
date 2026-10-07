import { Alert } from '@patternfly/react-core'

import {
  FORM_PROMPT_UNRESOLVED_DYNAMIC_OPTIONS_ALERT_BODY,
  FORM_PROMPT_UNRESOLVED_DYNAMIC_OPTIONS_ALERT_TITLE,
} from '../../../forms/formPromptDynamicOptions'

type FormPromptUnresolvedDynamicOptionsAlertProps = Readonly<{
  className?: string
}>

/** Shown when a loaded form prompt still has `options.source: dynamic` (unexpected after workflow materialization). */
export function FormPromptUnresolvedDynamicOptionsAlert({ className }: FormPromptUnresolvedDynamicOptionsAlertProps) {
  return (
    <Alert variant="warning" isInline title={FORM_PROMPT_UNRESOLVED_DYNAMIC_OPTIONS_ALERT_TITLE} className={className}>
      {FORM_PROMPT_UNRESOLVED_DYNAMIC_OPTIONS_ALERT_BODY}
    </Alert>
  )
}
