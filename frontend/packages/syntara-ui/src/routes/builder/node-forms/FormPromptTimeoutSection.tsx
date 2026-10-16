import { FormGroup, Stack, StackItem, Title } from '@patternfly/react-core'
import { useFormContext, useWatch } from 'react-hook-form'

import { useIsVersionView } from '../VersionViewContext'

import { FormPromptFallbackDecisionField } from './FormPromptFallbackDecisionField'
import type { FormPromptFormData } from './formPromptNodeFormSchema'
import { DurationInput } from './shared/DurationInput'
import { nodeHelp } from './shared/nodeFieldHelp'

export function FormPromptTimeoutSection() {
  const isVersionView = useIsVersionView()
  const { control, setValue } = useFormContext<FormPromptFormData>()
  const responseWindow = useWatch({ control, name: 'response_window' })

  return (
    <Stack hasGutter>
      <StackItem>
        <Title headingLevel="h3" size="md">
          Timeout
        </Title>
      </StackItem>
      <StackItem>
        <FormPromptFallbackDecisionField />
      </StackItem>
      <StackItem>
        <FormGroup
          label="Form submission window"
          labelHelp={nodeHelp.formPromptResponseWindow}
          fieldId="form-prompt-response-window"
        >
          <DurationInput
            value={responseWindow}
            onChange={(val) => setValue('response_window', val, { shouldDirty: true })}
            idPrefix="form-prompt-response-window"
            isDisabled={isVersionView}
          />
        </FormGroup>
      </StackItem>
    </Stack>
  )
}
