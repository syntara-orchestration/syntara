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
import { SynFormDefinitionPreview } from '../SynFormDefinitionPreview'

type FormFieldBuilderPreviewTabProps = Readonly<{
  submitLabel?: string | null
  cssOverrideSource?: string | null
  description?: string | null
}>

const FORM_BUILDER_PREVIEW_FALLBACK_DESCRIPTION = 'Preview of the configured form.'

export function FormFieldBuilderPreviewTab({
  submitLabel,
  cssOverrideSource,
  description,
}: FormFieldBuilderPreviewTabProps) {
  const { control } = useFormContext<FormDefinition>()
  const fields = useWatch({ control, name: 'fields' })

  const parsed = useMemo(() => safeParseFormDefinition({ fields }), [fields])
  const previewDescription = description?.trim() || FORM_BUILDER_PREVIEW_FALLBACK_DESCRIPTION

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
        <SynFormDefinitionPreview
          definition={parsed.data}
          description={previewDescription}
          submitLabel={submitLabel}
          cssOverrideSource={cssOverrideSource}
        />
      </StackItem>
    </Stack>
  )
}
