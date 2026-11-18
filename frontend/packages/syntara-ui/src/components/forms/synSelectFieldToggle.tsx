import { MenuToggle, type MenuToggleElement } from '@patternfly/react-core'
import type { Ref } from 'react'

export type SynSelectFieldToggleState = {
  fieldId?: string
  ariaLabel?: string
  displayLabel: string
  isOpen: boolean
  onToggle: () => void
  onBlur: () => void
  isDisabled?: boolean
  hasError: boolean
  describedBy?: string
}

type SynSelectFieldToggleProps = SynSelectFieldToggleState & {
  toggleRef: Ref<MenuToggleElement>
}

export function SynSelectFieldToggle({
  toggleRef,
  fieldId,
  ariaLabel,
  displayLabel,
  isOpen,
  onToggle,
  onBlur,
  isDisabled,
  hasError,
  describedBy,
}: Readonly<SynSelectFieldToggleProps>) {
  return (
    <MenuToggle
      ref={toggleRef}
      id={fieldId}
      aria-label={ariaLabel}
      aria-describedby={describedBy}
      onClick={onToggle}
      onBlur={onBlur}
      isExpanded={isOpen}
      isFullWidth
      isDisabled={isDisabled}
      status={hasError ? 'danger' : undefined}
    >
      {displayLabel}
    </MenuToggle>
  )
}
