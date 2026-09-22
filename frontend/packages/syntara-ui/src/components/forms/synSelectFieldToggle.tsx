import { MenuToggle, type MenuToggleElement } from '@patternfly/react-core'
import type { Ref } from 'react'

export type SynSelectFieldToggleState = {
  fieldId?: string
  displayLabel: string
  isOpen: boolean
  onToggle: () => void
  onBlur: () => void
  isDisabled?: boolean
  hasError: boolean
}

type SynSelectFieldToggleProps = SynSelectFieldToggleState & {
  toggleRef: Ref<MenuToggleElement>
}

export function SynSelectFieldToggle({
  toggleRef,
  fieldId,
  displayLabel,
  isOpen,
  onToggle,
  onBlur,
  isDisabled,
  hasError,
}: Readonly<SynSelectFieldToggleProps>) {
  return (
    <MenuToggle
      ref={toggleRef}
      id={fieldId}
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
