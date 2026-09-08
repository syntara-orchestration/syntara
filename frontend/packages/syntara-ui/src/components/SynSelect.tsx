import { Select, type SelectProps } from '@patternfly/react-core'

import { useCloseSelectOnOuterScroll } from '../hooks/useCloseSelectOnOuterScroll'

import { LONG_SELECT_MAX_MENU_HEIGHT, longSelectMenuPopperProps } from './longSelectMenu'
import longSelectMenuStyles from './longSelectMenu.module.css'

/** PatternFly `Select` props, plus Syntara menu defaults applied by {@link SynSelect}. */
export type SynSelectProps = SelectProps

/**
 * PatternFly `Select` with Syntara menu defaults. Prefer this over importing `Select`
 * from `@patternfly/react-core`. Enforced by `syntara/prefer-syn-select`.
 *
 * Defaults (pass an explicit prop to override):
 * - closes when the user scrolls outside the open menu
 * - `isScrollable`
 * - `maxMenuHeight` of {@link LONG_SELECT_MAX_MENU_HEIGHT} (`min(40vh, 25rem)`)
 * - popper `preventOverflow` so the menu stays in the viewport
 * - scroll containment on the menu (`overscroll-behavior: contain`)
 */
export function SynSelect({
  isOpen,
  onOpenChange,
  isScrollable = true,
  maxMenuHeight = LONG_SELECT_MAX_MENU_HEIGHT,
  popperProps,
  className,
  ...props
}: Readonly<SynSelectProps>) {
  const outerScrollRef = useCloseSelectOnOuterScroll(Boolean(isOpen), () => onOpenChange?.(false))
  const mergedClassName = [longSelectMenuStyles.containScroll, className].filter(Boolean).join(' ')

  return (
    <div ref={outerScrollRef}>
      <Select
        {...props}
        isOpen={isOpen}
        onOpenChange={onOpenChange}
        isScrollable={isScrollable}
        maxMenuHeight={maxMenuHeight}
        popperProps={{ ...longSelectMenuPopperProps, ...popperProps }}
        className={mergedClassName}
      />
    </div>
  )
}
