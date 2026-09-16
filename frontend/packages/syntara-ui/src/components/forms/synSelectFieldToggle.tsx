import { MenuToggle, type MenuToggleElement } from '@patternfly/react-core'
import type { Ref } from 'react'

export type SynSelectFieldToggleState = {
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
