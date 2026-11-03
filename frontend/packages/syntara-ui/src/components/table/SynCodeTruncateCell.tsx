import { Truncate } from '@patternfly/react-core'

import styles from './SynCodeTruncateCell.module.css'

/** Monospace table cell text with ellipsis and tooltip when truncated. */
export function SynCodeTruncateCell({ content }: Readonly<{ content: string }>) {
  return (
    <code className={styles.root}>
      <Truncate content={content} />
    </code>
  )
}
