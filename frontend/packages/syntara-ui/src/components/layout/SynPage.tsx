import { Stack, StackItem, type StackItemProps } from '@patternfly/react-core'
import type { ReactNode } from 'react'

import { flexCenteredBothAxes } from '../../app/flexCenteredBothAxes'

import styles from './SynPage.module.css'

/** Fills `CompassContent` (last child gets `flex-grow` in Compass CSS) so the page column + `SynPanel` heights resolve. */
export function SynPage(props: { children: React.ReactNode }) {
  return (
    <Stack hasGutter style={{ flex: 1, minHeight: 0 }}>
      {props.children}
    </Stack>
  )
}

export type SynPageBodyProps = Omit<StackItemProps, 'isFilled' | 'children'> & {
  children: ReactNode
  /** When true, merges `flexCenteredBothAxes` from `./flexCenteredBothAxes` for empty-state / loading layouts. */
  isCentered?: boolean
}

/**
 * Use as the **filled** row under `SynPage` (below `SynPageHeader`): `StackItem` + `isFilled` +
 * flex `min-height: 0` so full-height panels and inner scroll areas size correctly.
 * Pass `isCentered` for the usual flex-centered empty state, or `className` / `style` for overflow,
 * padding, and other layout tweaks (`style` merges after centered styles when `isCentered` is set).
 *
 * For the same flex behavior **inside** a nested `Stack` (e.g. builder side panels), prefer
 * `StackItem` + `isFilled` + `className={styles.main}` from `./SynPage.module.css` so the slot
 * is not misread as a page-level `SynPage` child.
 *
 * To stack multiple `SynPanel`s in this body (canvas + details), use `SynPanelStack` instead of
 * wrapping them in `overflow: hidden`.
 */
export function SynPageBody({ children, className, style, isCentered, ...rest }: SynPageBodyProps) {
  const mergedClass = [styles.main, className].filter(Boolean).join(' ')
  const mergedStyle = isCentered === true ? { ...flexCenteredBothAxes, ...style } : style
  return (
    <StackItem isFilled className={mergedClass} style={mergedStyle} {...rest}>
      {children}
    </StackItem>
  )
}
