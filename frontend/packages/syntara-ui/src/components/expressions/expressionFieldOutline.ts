import type { CSSProperties } from 'react'

// Set outlineWidth/outlineStyle/outlineColor individually instead of the `outline` shorthand —
// parsing `outline: '2px solid var(--x)'` incorrectly assigns the raw `var(--x)` string to all
// three properties. Renders identically either way.
export const DROP_TARGET_OUTLINE: CSSProperties = {
  outlineWidth: '2px',
  outlineStyle: 'solid',
  outlineColor: 'var(--pf-t--global--color--brand--default)',
  outlineOffset: '-2px',
}

export const DROP_TARGET_OUTLINE_ROUNDED: CSSProperties = {
  outlineWidth: '2px',
  outlineStyle: 'solid',
  outlineColor: 'var(--pf-t--global--color--brand--default)',
  borderRadius: 'var(--pf-t--global--border--radius--small)',
}
