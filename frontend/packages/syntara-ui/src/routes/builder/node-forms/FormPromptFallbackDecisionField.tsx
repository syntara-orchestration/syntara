import {
  Alert,
  Button,
  FormGroup,
  HelperText,
  HelperTextItem,
  MenuToggle,
  type MenuToggleElement,
  SelectList,
  SelectOption,
  Stack,
  StackItem,
} from '@patternfly/react-core'
import { useCallback, useState, type ReactElement, type Ref } from 'react'
import { Controller, useFormContext, useWatch } from 'react-hook-form'

import { DisabledWithTooltip } from '../../../components/DisabledWithTooltip'
import { SynSelect } from '../../../components/SynSelect'
import { useEffectiveContinueOnFailure } from '../hooks/useEffectiveContinueOnFailure'
import { useIsVersionView } from '../VersionViewContext'

import styles from './FallbackDecisionField.module.css'
import { getFallbackDecisionDisabledMessage } from './fallbackDecisionMessages'
import type { FormPromptFormData } from './formPromptNodeFormSchema'
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

type FallbackDecisionMenuToggleProps = Readonly<{
  toggleRef: Ref<MenuToggleElement>
  isOpen: boolean
  label: string
  isDisabled: boolean
  onToggle: () => void
}>

function FallbackDecisionMenuToggle({
  toggleRef,
  isOpen,
  label,
  isDisabled,
  onToggle,
}: FallbackDecisionMenuToggleProps) {
  return (
    <MenuToggle
      ref={toggleRef}
      onClick={onToggle}
      isExpanded={isOpen}
      isFullWidth
      isDisabled={isDisabled}
      aria-label="Fallback decision"
      aria-describedby={FALLBACK_HELPER_ID}
    >
      {label}
    </MenuToggle>
  )
}

function DisabledFallbackToggleWrap({ tooltip, children }: Readonly<{ tooltip: string; children: ReactElement }>) {
  return (
    <DisabledWithTooltip isDisabled content={tooltip}>
      <fieldset className={styles.disabledToggleWrap} aria-label="Fallback decision is disabled">
        {children}
      </fieldset>
    </DisabledWithTooltip>
  )
}

type FallbackDecisionSelectToggleProps = Readonly<{
  toggleRef: Ref<MenuToggleElement>
  isOpen: boolean
  value: string
  isDisabled: boolean
  tooltip?: string
  onToggle: () => void
}>

function FallbackDecisionSelectToggle({
  toggleRef,
  isOpen,
  value,
  isDisabled,
  tooltip,
  onToggle,
}: FallbackDecisionSelectToggleProps) {
  const toggle = (
    <FallbackDecisionMenuToggle
      toggleRef={toggleRef}
      isOpen={isOpen}
      label={fallbackToggleLabel(value)}
      isDisabled={isDisabled}
      onToggle={onToggle}
    />
  )
  if (!tooltip) return toggle
  return <DisabledFallbackToggleWrap tooltip={tooltip}>{toggle}</DisabledFallbackToggleWrap>
}

type FallbackDecisionSelectProps = Readonly<{
  value: string
  onChange: (value: 'submit' | 'fallback') => void
  isDisabled: boolean
  tooltip?: string
}>

function FallbackDecisionSelect({ value, onChange, isDisabled, tooltip }: FallbackDecisionSelectProps) {
  const [isOpen, setIsOpen] = useState(false)
  const handleToggle = useCallback(() => setIsOpen((prev) => !prev), [])
  const renderToggle = useCallback(
    (toggleRef: Ref<MenuToggleElement>) => (
      <FallbackDecisionSelectToggle
        toggleRef={toggleRef}
        isOpen={isOpen}
        value={value}
        isDisabled={isDisabled}
        tooltip={tooltip}
        onToggle={handleToggle}
      />
    ),
    [handleToggle, isDisabled, isOpen, tooltip, value]
  )

  return (
    <SynSelect
      id="form-prompt-fallback-decision"
      isOpen={isOpen}
      selected={value}
      shouldFocusToggleOnSelect
      onSelect={(_event, val: string | number | undefined) => {
        onChange(parseFormPromptFallbackDecision(val))
        setIsOpen(false)
      }}
      onOpenChange={setIsOpen}
      toggle={renderToggle}
    >
      <SelectList>
        <SelectOption value="fallback">Fallback path (default)</SelectOption>
        <SelectOption value="submit">Submitted path</SelectOption>
      </SelectList>
    </SynSelect>
  )
}

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
                  <FallbackDecisionSelect
                    value={timeoutDecision}
                    onChange={field.onChange}
                    isDisabled={isDisabled}
                    tooltip={disabledGuidance}
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
