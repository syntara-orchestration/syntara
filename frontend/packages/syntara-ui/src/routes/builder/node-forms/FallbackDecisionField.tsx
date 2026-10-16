import { Button, FormGroup, HelperText, HelperTextItem, Stack, StackItem } from '@patternfly/react-core'
import { Controller, useFormContext } from 'react-hook-form'

import { useEffectiveContinueOnFailure } from '../hooks/useEffectiveContinueOnFailure'
import { useIsVersionView } from '../VersionViewContext'

import type { ApprovalFormData } from './approvalFormSchema'
import { getFallbackDecisionDisabledMessage } from './fallbackDecisionMessages'
import { FallbackDecisionSynSelect } from './shared/FallbackDecisionSynSelect'
import { nodeHelp } from './shared/nodeFieldHelp'
import { APPROVAL_FALLBACK_ENABLE_LINK, APPROVAL_FALLBACK_ENABLED_HELPER } from './shared/nodeFieldHelpText'

const FALLBACK_HELPER_ID = 'approval-fallback-decision-helper'

function fallbackToggleLabel(value: string): string {
  return value === 'reject' ? 'Reject (default)' : 'Approve'
}

function parseFallbackDecision(value: string | number | undefined): 'approve' | 'reject' {
  return value === 'approve' ? 'approve' : 'reject'
}

const APPROVAL_FALLBACK_OPTIONS = [
  { value: 'reject', label: 'Reject (default)' },
  { value: 'approve', label: 'Approve' },
] as const

/**
 * Approval Parameters control for fallback decision. Disabled with warning
 * copy when effective continue on failure is off.
 */
export function FallbackDecisionField() {
  const isVersionView = useIsVersionView()
  const { control, setValue } = useFormContext<ApprovalFormData>()
  const { isEffectivelyEnabled, source } = useEffectiveContinueOnFailure()

  const disabledMessage = getFallbackDecisionDisabledMessage(source)
  const showDisabledGuidance = !isVersionView && !isEffectivelyEnabled
  const isDisabled = isVersionView || !isEffectivelyEnabled
  const disabledGuidance = showDisabledGuidance ? disabledMessage : undefined

  function handleEnableContinueOnFailure() {
    setValue('settings.continue_on_failure', true, { shouldDirty: true })
  }

  return (
    <FormGroup label="Fallback decision" labelHelp={nodeHelp.approvalFallback} fieldId="approval-fallback-decision">
      <Stack hasGutter>
        <StackItem>
          <Controller
            control={control}
            name="fallback_decision"
            render={({ field }) => (
              <FallbackDecisionSynSelect
                id="approval-fallback-decision"
                helperId={FALLBACK_HELPER_ID}
                value={field.value ?? 'reject'}
                onChange={field.onChange}
                isDisabled={isDisabled}
                tooltip={disabledGuidance}
                options={APPROVAL_FALLBACK_OPTIONS}
                parseValue={parseFallbackDecision}
                formatToggleLabel={fallbackToggleLabel}
              />
            )}
          />
        </StackItem>
        <StackItem>
          <HelperText isLiveRegion id={FALLBACK_HELPER_ID}>
            <HelperTextItem variant={isEffectivelyEnabled ? 'default' : 'warning'}>
              {isEffectivelyEnabled ? APPROVAL_FALLBACK_ENABLED_HELPER : disabledMessage}
              {showDisabledGuidance ? (
                <>
                  {' '}
                  <Button variant="link" isInline type="button" onClick={handleEnableContinueOnFailure}>
                    {APPROVAL_FALLBACK_ENABLE_LINK}
                  </Button>
                </>
              ) : null}
            </HelperTextItem>
          </HelperText>
        </StackItem>
      </Stack>
    </FormGroup>
  )
}
