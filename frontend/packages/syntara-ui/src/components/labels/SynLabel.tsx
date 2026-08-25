import { Label, type LabelProps } from '@patternfly/react-core'

/**
 * Standard application label with UX-driven defaults.
 *
 * Use for all system-generated labels: statuses, categories, metadata badges, and counts.
 * Pass `status` and `icon` props for status indicators.
 *
 * For user-authored tags (workflow tags, user-entered values), use `SynUserTag` instead.
 */
export function SynLabel({ isCompact = true, variant = 'filled', ...rest }: Readonly<LabelProps>) {
  return <Label isCompact={isCompact} variant={variant} {...rest} />
}
