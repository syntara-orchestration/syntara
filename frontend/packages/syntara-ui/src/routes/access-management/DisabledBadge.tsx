import { NxLabel } from '../../components/labels/NxLabel'

/** Inline "Disabled" label shown next to disabled user accounts. */
export function DisabledBadge() {
  return (
    <NxLabel variant="outline" style={{ marginInlineStart: 'var(--pf-t--global--spacer--sm)' }}>
      Disabled
    </NxLabel>
  )
}
