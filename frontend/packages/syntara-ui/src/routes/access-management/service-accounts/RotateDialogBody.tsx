import {
  Alert,
  Content,
  FormGroup,
  MenuToggle,
  SelectList,
  SelectOption,
  Stack,
  StackItem,
} from '@patternfly/react-core'
import type { MenuToggleElement } from '@patternfly/react-core'
import { type Ref, useCallback, useState } from 'react'

import { SynSelect } from '../../../components/SynSelect'

import { computeRemainingGracePeriod, DEFAULT_GRACE_PERIOD, GRACE_PERIOD_OPTIONS } from './rotateDialogUtils'
import { serviceAccountHelp } from './serviceAccountFieldHelp'
import type { ServiceAccountCredentialRead } from './serviceAccountTypes'

export function RotateDialogBody({
  credential,
  gracePeriod,
  onGracePeriodChange,
}: Readonly<{
  credential: ServiceAccountCredentialRead | null
  gracePeriod: number
  onGracePeriodChange: (value: number) => void
}>) {
  const [isSelectOpen, setIsSelectOpen] = useState(false)

  const activeGracePeriod = credential?.old_secret_valid_until
    ? computeRemainingGracePeriod(credential.old_secret_valid_until)
    : null

  const selectedLabel =
    GRACE_PERIOD_OPTIONS.find((opt) => opt.value === gracePeriod)?.label ??
    GRACE_PERIOD_OPTIONS.find((opt) => opt.value === DEFAULT_GRACE_PERIOD)!.label

  const renderToggle = useCallback(
    (ref: Ref<MenuToggleElement>) => (
      <MenuToggle ref={ref} onClick={() => setIsSelectOpen((prev) => !prev)} isExpanded={isSelectOpen} isFullWidth>
        {selectedLabel}
      </MenuToggle>
    ),
    [selectedLabel, isSelectOpen]
  )

  return (
    <Stack hasGutter>
      <StackItem>
        <Content component="p">
          A new client secret will be generated for credential <strong>{credential?.identifier}</strong>.
        </Content>
      </StackItem>

      {activeGracePeriod && (
        <StackItem>
          <Alert variant="warning" isInline title="Active grace period will be replaced">
            This credential has a previous secret that is still valid for{' '}
            <strong>{activeGracePeriod.remainingLabel}</strong> (until {activeGracePeriod.expiryFormatted}). Rotating
            again now will immediately invalidate that previous secret.
          </Alert>
        </StackItem>
      )}

      <StackItem>
        <FormGroup
          label="Current secret grace period"
          fieldId="rotate-grace-period"
          labelHelp={serviceAccountHelp.gracePeriod}
        >
          <SynSelect
            id="rotate-grace-period"
            aria-label="Current secret grace period"
            isOpen={isSelectOpen}
            onOpenChange={setIsSelectOpen}
            onSelect={(_e, val) => {
              onGracePeriodChange(Number(val))
              setIsSelectOpen(false)
            }}
            selected={gracePeriod}
            popperProps={{ appendTo: 'inline' }}
            toggle={renderToggle}
            shouldFocusToggleOnSelect
          >
            <SelectList>
              {GRACE_PERIOD_OPTIONS.map((opt) => (
                <SelectOption key={opt.value} value={opt.value} isSelected={opt.value === gracePeriod}>
                  {opt.label}
                </SelectOption>
              ))}
            </SelectList>
          </SynSelect>
        </FormGroup>
      </StackItem>
    </Stack>
  )
}
