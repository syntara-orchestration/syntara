import { Truncate } from '@patternfly/react-core'
import { Children, cloneElement, isValidElement, useRef, type ReactNode, type RefObject } from 'react'

import { SynLink } from '../SynLink'

import styles from './LinkCell.module.css'

type TruncateElementProps = { tooltipProps?: { triggerRef?: RefObject<HTMLElement | null> } }

/**
 * When LinkCell wraps PatternFly Truncate, attach the tooltip to the link so
 * keyboard users get one tab stop and the tooltip on link focus (not a second
 * tab into Truncate's inner span). Truncate still owns when the tooltip shows.
 */
function wireTruncateChild(children: ReactNode, linkRef: RefObject<HTMLAnchorElement | null>): ReactNode {
  const child = Children.only(children)
  if (!isValidElement<TruncateElementProps>(child) || child.type !== Truncate) {
    return children
  }

  const existingTooltipProps = child.props.tooltipProps ?? {}
  return cloneElement(child, {
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
