import { Alert, Stack, StackItem } from '@patternfly/react-core'
import type { FormDefinition } from '@syntara/contracts'
import { useMemo } from 'react'
import { useFormContext, useWatch } from 'react-hook-form'

import { safeParseFormDefinition } from '../../../forms'
import {
  formDefinitionHasUnresolvedDynamicOptions,
  FORM_PROMPT_PREVIEW_DYNAMIC_OPTIONS_ALERT_BODY,
  FORM_PROMPT_PREVIEW_DYNAMIC_OPTIONS_ALERT_TITLE,
} from '../../../forms/formPromptDynamicOptions'
import { SynDynamicForm } from '../SynDynamicForm'

export function FormFieldBuilderPreviewTab() {
  const { control } = useFormContext<FormDefinition>()
  const fields = useWatch({ control, name: 'fields' })

  const parsed = useMemo(() => safeParseFormDefinition({ fields }), [fields])

  if (!parsed.success) {
    return (
      <Stack hasGutter>
        <StackItem>
          <Alert variant="warning" title="Fix validation errors to preview the form" isInline />
        </StackItem>
        {parsed.errors.map((error) => (
          <StackItem key={`${error.field}-${error.message}`}>
            <Alert variant="warning" title={error.message} isInline />
          </StackItem>
        ))}
      </Stack>
    )
  }

  const showDynamicOptionsNotice = parsed.success && formDefinitionHasUnresolvedDynamicOptions(parsed.data)

  return (
    <Stack hasGutter>
      {showDynamicOptionsNotice ? (
        <StackItem>
          <Alert variant="info" isInline title={FORM_PROMPT_PREVIEW_DYNAMIC_OPTIONS_ALERT_TITLE}>
            {FORM_PROMPT_PREVIEW_DYNAMIC_OPTIONS_ALERT_BODY}
          </Alert>
        </StackItem>
      ) : null}
      <StackItem>
        <SynDynamicForm
          definition={parsed.data}
          hideSubmitButton
          isReadOnly
          onSubmit={() => undefined}
          description="Preview of the configured form."
        />
      </StackItem>
    </Stack>
  )
}
