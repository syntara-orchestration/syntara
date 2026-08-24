import type { CSSProperties } from 'react'

/**
 * Layout style objects for full-height panel content.
 *
 * - **SynPanelContentStack** composes `panelContentStackStyle` (see `SynPanelContentStack.tsx`) — prefer
 *   that component over spreading the style object directly.
 * - **Standalone exports** are for call sites that need a raw `style` object without the wrapper.
 *
 * PatternFly `Stack` props for the main content column inside `SynPanel` with `isFullHeight`.
 * `height: '100%'` alone often fails to fill a flex parent; `flex: 1` + `minHeight: 0` opts into
 * correct flex shrink/growth so nested `NxScrollableTableContainer` / scroll regions get a real height.
 */
export const panelContentStackStyle = {
  height: '100%',
  flex: 1,
  minHeight: 0,
  minWidth: 0,
} as const satisfies CSSProperties

/** Top-level list pages: small horizontal inset so the filter bar and table don't touch the panel edge. */
export const panelContentStackInsetStyle = {
  ...panelContentStackStyle,
  padding: '0 var(--pf-t--global--spacer--sm)',
} as const satisfies CSSProperties
