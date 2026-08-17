/**
 * Reusable help popover component for expression builder
 * Displays a question mark icon that opens a popover with help content
 */

import { Button, Popover } from '@patternfly/react-core'
import type { ReactNode } from 'react'

import { FieldHelpIcon } from '../FieldHelpIcon'

type HelpPopoverProps = {
  /** Accessible label for the help button */
  ariaLabel: string
  /** Header text for the popover */
  headerContent?: string
  /** Body content for the popover */
  bodyContent: ReactNode
}

/**
 * Help popover component
 * Renders a question mark icon that opens a popover with help content
 */
export function HelpPopover({ ariaLabel, headerContent, bodyContent }: HelpPopoverProps) {
  return (
    <Popover aria-label={ariaLabel} headerContent={headerContent} bodyContent={bodyContent} triggerAction="click">
      <Button variant="plain" aria-label={ariaLabel} onClick={(e) => e.preventDefault()} icon={<FieldHelpIcon />} />
    </Popover>
  )
}
