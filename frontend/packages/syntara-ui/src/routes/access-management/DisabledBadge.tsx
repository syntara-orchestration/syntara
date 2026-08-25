import { SynLabel } from '../../components/labels/SynLabel'

/** Inline "Disabled" label shown next to disabled user accounts. */
export function DisabledBadge() {
  return (
    <SynLabel variant="outline" style={{ marginInlineStart: 'var(--pf-t--global--spacer--sm)' }}>
      Disabled
    </SynLabel>
  )
}
