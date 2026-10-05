import { Truncate } from '@patternfly/react-core'

import styles from './CodeTruncateCell.module.css'

/** Monospace table cell text with ellipsis and tooltip when truncated. */
export function CodeTruncateCell({ content }: Readonly<{ content: string }>) {
  return (
    <code className={styles.root}>
      <Truncate content={content} />
    </code>
  )
}
