import { Alert, Button, FormGroup, HelperText, HelperTextItem, Stack, StackItem } from '@patternfly/react-core'
import { Controller, useFormContext, useWatch } from 'react-hook-form'

import { useEffectiveContinueOnFailure } from '../hooks/useEffectiveContinueOnFailure'
import { useIsVersionView } from '../VersionViewContext'

import { getFallbackDecisionDisabledMessage } from './fallbackDecisionMessages'
import type { FormPromptFormData } from './formPromptNodeFormSchema'
import { FallbackDecisionSynSelect } from './shared/FallbackDecisionSynSelect'
import { nodeHelp } from './shared/nodeFieldHelp'
import {
  FORM_PROMPT_FALLBACK_DEFAULTS_HELPER,
  FORM_PROMPT_FALLBACK_ENABLE_LINK,
  FORM_PROMPT_FALLBACK_ENABLED_HELPER,
} from './shared/nodeFieldHelpText'

const FALLBACK_HELPER_ID = 'form-prompt-fallback-decision-helper'

function fallbackToggleLabel(value: string): string {
  return value === 'submit' ? 'Submitted path' : 'Fallback path (default)'
}

function parseFormPromptFallbackDecision(value: string | number | undefined): 'submit' | 'fallback' {
  return value === 'submit' ? 'submit' : 'fallback'
}

const FORM_PROMPT_FALLBACK_OPTIONS = [
  { value: 'fallback', label: 'Fallback path (default)' },
  { value: 'submit', label: 'Submitted path' },
] as const

export function FormPromptFallbackDecisionField() {
  const isVersionView = useIsVersionView()
  const { control, setValue } = useFormContext<FormPromptFormData>()
  const { isEffectivelyEnabled, source } = useEffectiveContinueOnFailure()
  const fallbackDecision = useWatch({ control, name: 'fallback_decision' })
  const timeoutDecision = isEffectivelyEnabled ? (fallbackDecision ?? 'fallback') : 'submit'

  const disabledMessage = getFallbackDecisionDisabledMessage(source)
  const showDisabledGuidance = !isVersionView && !isEffectivelyEnabled
  const isDisabled = isVersionView || !isEffectivelyEnabled
  const disabledGuidance = showDisabledGuidance ? disabledMessage : undefined
  const showDefaultsCallout = isEffectivelyEnabled && fallbackDecision === 'submit'

  function handleEnableContinueOnFailure() {
    setValue('settings.continue_on_failure', true, { shouldDirty: true })
  }

  return (
    <Stack hasGutter>
      <StackItem>
        <FormGroup
          label="Fallback decision"
          labelHelp={nodeHelp.formPromptFallback}
          fieldId="form-prompt-fallback-decision"
        >
          <Stack hasGutter>
            <StackItem>
              <Controller
                control={control}
                name="fallback_decision"
                render={({ field }) => (
                  <FallbackDecisionSynSelect
                    id="form-prompt-fallback-decision"
                    helperId={FALLBACK_HELPER_ID}
                    value={timeoutDecision}
                    onChange={field.onChange}
                    isDisabled={isDisabled}
                    tooltip={disabledGuidance}
                    options={FORM_PROMPT_FALLBACK_OPTIONS}
                    parseValue={parseFormPromptFallbackDecision}
                    formatToggleLabel={fallbackToggleLabel}
                  />
                )}
              />
            </StackItem>
            <StackItem>
              <HelperText isLiveRegion id={FALLBACK_HELPER_ID}>
                <HelperTextItem variant={isEffectivelyEnabled ? 'default' : 'warning'}>
                  {isEffectivelyEnabled ? FORM_PROMPT_FALLBACK_ENABLED_HELPER : disabledMessage}
                  {showDisabledGuidance ? (
                    <>
                      {' '}
                      <Button variant="link" isInline type="button" onClick={handleEnableContinueOnFailure}>
                        {FORM_PROMPT_FALLBACK_ENABLE_LINK}
                      </Button>
                    </>
                  ) : null}
                </HelperTextItem>
              </HelperText>
            </StackItem>
          </Stack>
        </FormGroup>
      </StackItem>
      {showDefaultsCallout ? (
        <StackItem>
          <Alert variant="info" title="Default field values" isInline isPlain>
            {FORM_PROMPT_FALLBACK_DEFAULTS_HELPER}
          </Alert>
        </StackItem>
      ) : null}
    </Stack>
  )
}
