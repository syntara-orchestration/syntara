import { Truncate } from '@patternfly/react-core'
import { cloneElement, isValidElement, useRef, type ReactNode, type RefObject } from 'react'

import { SynLink } from '../SynLink'

import styles from './LinkCell.module.css'

type TruncateElementProps = { tooltipProps?: { triggerRef?: RefObject<HTMLElement | null> } }

/**
 * When LinkCell wraps PatternFly Truncate, attach the tooltip to the link so
 * keyboard users get one tab stop and the tooltip on link focus (not a second
 * tab into Truncate's inner span). Truncate still owns when the tooltip shows.
 */
function wireTruncateChild(children: ReactNode, linkRef: RefObject<HTMLAnchorElement | null>): ReactNode {
  if (!isValidElement<TruncateElementProps>(children) || children.type !== Truncate) {
    return children
  }

  const existingTooltipProps = children.props.tooltipProps ?? {}
  return cloneElement(children, {
    tooltipProps: { ...existingTooltipProps, triggerRef: linkRef },
  })
}

/** Renders a table cell value as a client-side router link. */
export function LinkCell(props: Readonly<{ href: string; children: React.ReactNode }>) {
  const linkRef = useRef<HTMLAnchorElement>(null)

  return (
    <SynLink ref={linkRef} to={props.href} className={styles.root}>
      {wireTruncateChild(props.children, linkRef)}
    </SynLink>
  )
}
