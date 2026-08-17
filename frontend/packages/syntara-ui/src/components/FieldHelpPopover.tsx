import { Button, Popover } from '@patternfly/react-core'
import { type ReactNode, useRef } from 'react'

import { FieldHelpIcon } from './FieldHelpIcon'
import styles from './FieldHelpIcon.module.css'

export type FieldHelpPopoverProps = Readonly<{
  /** Body content for the popover (plain text or rich React nodes). */
  helpText: ReactNode
  /** Optional header shown at the top of the popover. */
  headerContent?: ReactNode
  /** Accessible name for the popover dialog. Defaults to "Field help". */
  'aria-label'?: string
}>

/**
 * Label help for FormGroup: RhUi question-mark icon + Popover with shared ref.
 *
 * Pass as `labelHelp` on FormGroup:
 * ```tsx
 * <FormGroup label="Issuer URL" labelHelp={<FieldHelpPopover helpText="…" headerContent="Issuer URL" />}>
 * ```
 */
export function FieldHelpPopover({
  helpText,
  headerContent,
  'aria-label': ariaLabel = 'Field help',
}: FieldHelpPopoverProps) {
  const triggerRef = useRef<HTMLButtonElement>(null)
  const triggerAriaLabel = typeof headerContent === 'string' ? `More info for ${headerContent}` : 'More info'

  return (
    <Popover triggerRef={triggerRef} bodyContent={helpText} headerContent={headerContent} aria-label={ariaLabel}>
      <Button
        ref={triggerRef}
        variant="plain"
        aria-label={triggerAriaLabel}
        className={styles.trigger}
        icon={<FieldHelpIcon />}
      />
    </Popover>
  )
}
