import { RhUiQuestionMarkCircleIcon } from '@patternfly/react-icons'

import styles from './FieldHelpIcon.module.css'

/** Shared help-trigger glyph for form labels and field help popovers. */
export function FieldHelpIcon() {
  return <RhUiQuestionMarkCircleIcon className={styles.icon} />
}
