import type { RunOptions } from 'axe-core'

/**
 * PatternFly 6 Tabs set `aria-controls` to panel ids that exist in real browsers but
 * are not resolvable in happy-dom test environments. See ApprovalNodeForm.test.tsx and
 * TriggerNodeForm.test.tsx for the same limitation.
 */
export const axeOptionsPatternFlyTabs: RunOptions = {
  rules: {
    'aria-valid-attr-value': { enabled: false },
  },
}
