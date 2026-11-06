import { MenuToggle, type MenuToggleElement, SelectList, SelectOption } from '@patternfly/react-core'
import { useCallback, useState, type ReactElement, type Ref } from 'react'

import { DisabledWithTooltip } from '../../../../components/DisabledWithTooltip'
import { SynSelect } from '../../../../components/SynSelect'
import styles from '../FallbackDecisionField.module.css'

type FallbackDecisionOption = Readonly<{
  value: string
  label: string
}>

type FallbackDecisionSynSelectProps<T extends string> = Readonly<{
  id: string
  helperId: string
  value: string
  onChange: (value: T) => void
  isDisabled: boolean
  tooltip?: string
  options: readonly FallbackDecisionOption[]
  parseValue: (value: string | number | undefined) => T
  formatToggleLabel: (value: string) => string
}>

function DisabledFallbackToggleWrap({ tooltip, children }: Readonly<{ tooltip: string; children: ReactElement }>) {
  return (
    <DisabledWithTooltip isDisabled content={tooltip}>
      <fieldset className={styles.disabledToggleWrap} aria-label="Fallback decision is disabled">
        {children}
      </fieldset>
    </DisabledWithTooltip>
  )
}

type FallbackDecisionMenuToggleProps = Readonly<{
  toggleRef: Ref<MenuToggleElement>
  helperId: string
  isOpen: boolean
  label: string
  isDisabled: boolean
  onToggle: () => void
}>

function FallbackDecisionMenuToggle({
  toggleRef,
  helperId,
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
      aria-describedby={helperId}
    >
      {label}
    </MenuToggle>
  )
}

type FallbackDecisionSelectToggleProps = Readonly<{
  toggleRef: Ref<MenuToggleElement>
  helperId: string
  isOpen: boolean
  value: string
  isDisabled: boolean
  tooltip?: string
  formatToggleLabel: (value: string) => string
  onToggle: () => void
}>

function FallbackDecisionSelectToggle({
  toggleRef,
  helperId,
  isOpen,
  value,
  isDisabled,
  tooltip,
  formatToggleLabel,
  onToggle,
}: FallbackDecisionSelectToggleProps) {
  const toggle = (
    <FallbackDecisionMenuToggle
      toggleRef={toggleRef}
      helperId={helperId}
      isOpen={isOpen}
      label={formatToggleLabel(value)}
      isDisabled={isDisabled}
      onToggle={onToggle}
    />
  )
  if (!tooltip) return toggle
  return <DisabledFallbackToggleWrap tooltip={tooltip}>{toggle}</DisabledFallbackToggleWrap>
}

export function FallbackDecisionSynSelect<T extends string>({
  id,
  helperId,
  value,
  onChange,
  isDisabled,
  tooltip,
  options,
  parseValue,
  formatToggleLabel,
}: FallbackDecisionSynSelectProps<T>) {
  const [isOpen, setIsOpen] = useState(false)
  const handleToggle = useCallback(() => setIsOpen((prev) => !prev), [])
  const renderToggle = useCallback(
    (toggleRef: Ref<MenuToggleElement>) => (
      <FallbackDecisionSelectToggle
        toggleRef={toggleRef}
        helperId={helperId}
        isOpen={isOpen}
        value={value}
        isDisabled={isDisabled}
        tooltip={tooltip}
        formatToggleLabel={formatToggleLabel}
        onToggle={handleToggle}
      />
    ),
    [formatToggleLabel, handleToggle, helperId, isDisabled, isOpen, tooltip, value]
  )

  return (
    <SynSelect
      id={id}
      isOpen={isOpen}
      selected={value}
      shouldFocusToggleOnSelect
      onSelect={(_event, val: string | number | undefined) => {
        onChange(parseValue(val))
        setIsOpen(false)
      }}
      onOpenChange={setIsOpen}
      toggle={renderToggle}
    >
      <SelectList>
        {options.map((option) => (
          <SelectOption key={option.value} value={option.value}>
            {option.label}
          </SelectOption>
        ))}
      </SelectList>
    </SynSelect>
  )
}
