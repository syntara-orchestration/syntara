import { Stack, StackItem, type StackItemProps, type StackProps } from '@patternfly/react-core'
import type { CSSProperties } from 'react'

import styles from './SynPanelStack.module.css'

export type SynPanelStackProps = Omit<StackProps, 'children'> & {
  children: StackProps['children']
}

export type SynPanelStackItemProps = StackItemProps

/**
 * Full-height column for stacking sibling `SynPanel`s (canvas + details, editor + run panel).
 *
 * Uses `min-height: 0` and keeps `overflow: visible` so PatternFly panel `box-shadow` is not
 * clipped. Clip inside each panel instead (scrollable `PanelMain`, React Flow viewport).
 *
 * `overflow: visible` is applied after `style` so a caller `overflow: hidden` cannot clip shadows.
 */
export function SynPanelStack({ className, style, ...props }: SynPanelStackProps) {
  const mergedClass = [styles.stack, className].filter(Boolean).join(' ')
  const mergedStyle: CSSProperties = { ...style, overflow: 'visible' }
  return <Stack className={mergedClass} style={mergedStyle} {...props} />
}

/**
 * Slot in `SynPanelStack`. Use `isFilled` for the flexible pane (canvas) and a sized item
 * for a fixed pane (details). Same overflow rule as `SynPanelStack`.
 */
export function SynPanelStackItem({ isFilled, className, style, ...props }: SynPanelStackItemProps) {
  const slotClass = isFilled === true ? styles.filled : styles.fixed
  const mergedClass = [slotClass, className].filter(Boolean).join(' ')
  const mergedStyle: CSSProperties = { ...style, overflow: 'visible' }
  return <StackItem isFilled={isFilled} className={mergedClass} style={mergedStyle} {...props} />
}
