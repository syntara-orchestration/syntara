import { Link } from '@tanstack/react-router'
import type { MouseEvent, ReactNode } from 'react'

type HistoryListItemLinkProps = Readonly<{
  to: string
  isSelected?: boolean
  onSelect: () => void
  children?: ReactNode
  className?: string
  'aria-label'?: string
  'data-item-id'?: string
}>

function isModifiedClick(event: MouseEvent<HTMLAnchorElement>): boolean {
  return event.metaKey || event.altKey || event.ctrlKey || event.shiftKey
}

/**
 * PatternFly Simple List item rendered as a TanStack Router `<Link>` so rows get
 * link semantics (open in new tab, SR role, client-side routing) while unmodified
 * left-click still runs `onSelect`. SynLink is a PF Button, so it cannot be used here.
 */
export function HistoryListItemLink({
  to,
  isSelected = false,
  onSelect,
  children,
  className,
  'aria-label': ariaLabel,
  'data-item-id': dataItemId,
}: HistoryListItemLinkProps) {
  const selectedClass = isSelected ? ' pf-m-current' : ''
  const extraClass = className ? ` ${className}` : ''

  return (
    <Link
      // TanStack Router expects literal route strings; history hrefs are dynamic
      to={to}
      className={`pf-v6-c-simple-list__item-link${selectedClass}${extraClass}`.trim()}
      aria-current={isSelected ? 'page' : undefined}
      aria-label={ariaLabel}
      data-item-id={dataItemId}
      onClick={(event) => {
        if (isModifiedClick(event)) {
          return
        }
        event.preventDefault()
        onSelect()
      }}
    >
      {children}
    </Link>
  )
}
