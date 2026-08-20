import { type LabelProps } from '@patternfly/react-core'

import { SynLabel } from './SynLabel'

type SynUserTagProps = Omit<LabelProps, 'variant'>

/**
 * Outline label for user-authored content — workflow tags, user-entered values.
 *
 * For system-generated labels (statuses, categories, metadata), use `SynLabel` instead.
 */
export function SynUserTag(props: Readonly<SynUserTagProps>) {
  return <SynLabel variant="outline" {...props} />
}
