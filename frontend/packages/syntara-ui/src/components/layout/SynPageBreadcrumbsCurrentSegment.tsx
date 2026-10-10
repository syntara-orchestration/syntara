import { Tooltip } from '@patternfly/react-core'

import styles from './SynPageBreadcrumbs.module.css'

type BreadcrumbCurrentSegmentProps = Readonly<{
  label: string
}>

/** Current-page breadcrumb label: ellipsis truncation with full text in a flip-enabled tooltip. */
export function BreadcrumbCurrentSegment({ label }: BreadcrumbCurrentSegmentProps) {
  return (
    <Tooltip content={label} enableFlip maxWidth="min(100vw - 2rem, 24rem)">
      <span className={styles.currentSegment} data-testid="breadcrumb-current-segment">
        {label}
      </span>
    </Tooltip>
  )
}
