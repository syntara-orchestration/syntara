import { Select, type SelectProps } from '@patternfly/react-core'

import { useCloseSelectOnOuterScroll } from '../hooks/useCloseSelectOnOuterScroll'

export type SynSelectProps = SelectProps

/**
 * PatternFly Select that closes when the user scrolls outside the open menu
 * (page, modal body, or other scroll parents). Prefer this over bare `Select`
 * for app selects so dismiss-on-outer-scroll stays consistent.
 */
export function SynSelect({ isOpen, onOpenChange, ...props }: SynSelectProps) {
  const outerScrollRef = useCloseSelectOnOuterScroll(Boolean(isOpen), () => onOpenChange?.(false))

  return (
    <div ref={outerScrollRef}>
      <Select isOpen={isOpen} onOpenChange={onOpenChange} {...props} />
    </div>
  )
}
