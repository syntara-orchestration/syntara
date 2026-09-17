import type { CSSProperties } from 'react'

/**
 * Flex layout (`display: flex`) with `align-items` and `justify-content` both `center` — typical
 * empty-state / loading pattern. Prefer `SynPageBody` with `isCentered` for page-level slots; use
 * this object for nested slots (e.g. `StackItem` + `isFilled`).
 */
export const flexCenteredBothAxes = {
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
} as const satisfies CSSProperties
