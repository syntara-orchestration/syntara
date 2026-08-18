import {
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
import { Controller, useFormContext } from 'react-hook-form'

import { DisabledWithTooltip } from '../../../components/DisabledWithTooltip'
import { NxSelect } from '../../../components/NxSelect'
import { useEffectiveContinueOnFailure } from '../hooks/useEffectiveContinueOnFailure'
import { useIsVersionView } from '../VersionViewContext'

import type { ApprovalFormData } from './approvalFormSchema'
import styles from './FallbackDecisionField.module.css'
import { getFallbackDecisionDisabledMessage } from './fallbackDecisionMessages'
import { nodeHelp } from './shared/nodeFieldHelp'
import { APPROVAL_FALLBACK_ENABLE_LINK, APPROVAL_FALLBACK_ENABLED_HELPER } from './shared/nodeFieldHelpText'

const FALLBACK_HELPER_ID = 'approval-fallback-decision-helper'

function fallbackToggleLabel(value: string): string {
  return value === 'reject' ? 'Reject (default)' : 'Approve'
}

function parseFallbackDecision(value: string | number | undefined): 'approve' | 'reject' {
  return value === 'approve' ? 'approve' : 'reject'
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
  onChange: (value: 'approve' | 'reject') => void
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
    <NxSelect
      id="approval-fallback-decision"
      isOpen={isOpen}
      selected={value}
      shouldFocusToggleOnSelect
      onSelect={(_event, val: string | number | undefined) => {
        onChange(parseFallbackDecision(val))
        setIsOpen(false)
      }}
      onOpenChange={setIsOpen}
      toggle={renderToggle}
    >
      <SelectList>
        <SelectOption value="reject">Reject (default)</SelectOption>
        <SelectOption value="approve">Approve</SelectOption>
      </SelectList>
    </NxSelect>
  )
}

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
              <FallbackDecisionSelect
                value={field.value ?? 'reject'}
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
