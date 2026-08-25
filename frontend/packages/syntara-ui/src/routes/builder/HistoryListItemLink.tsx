import { Link } from '@tanstack/react-router'
import type { ComponentProps, MouseEvent, ReactNode } from 'react'

type TanStackTo = ComponentProps<typeof Link>['to']

type HistoryListItemLinkProps = Readonly<{
  to: string
  isSelected?: boolean
  onSelect: () => void
  children?: ReactNode
  className?: string
  'aria-label'?: string
  'data-item-id'?: string
  /**
   * When true the `<a>` is rendered without PF's `pf-v6-c-simple-list__item-link`
   * class so it can be absolutely-positioned as an overlay without PF's
   * `position: relative` fighting the overlay layout.
   */
  overlay?: boolean
}>

function isModifiedClick(event: MouseEvent<HTMLAnchorElement>): boolean {
  return event.metaKey || event.altKey || event.ctrlKey || event.shiftKey
}

/**
 * PatternFly Simple List item rendered as a TanStack Router `<Link>` so rows get
 * link semantics (open in new tab, SR role, client-side routing) while unmodified
 * left-click still runs `onSelect`. NxLink is a PF Button, so it cannot be used here.
 */
export function HistoryListItemLink({
  to,
  isSelected = false,
  onSelect,
  children,
  className,
  'aria-label': ariaLabel,
  'data-item-id': dataItemId,
  overlay = false,
}: HistoryListItemLinkProps) {
  const pfClass = overlay ? '' : 'pf-v6-c-simple-list__item-link'
  const selectedClass = isSelected ? ' pf-m-current' : ''
  const extraClass = className ? ` ${className}` : ''

  return (
    <Link
      // TanStack Router expects literal route strings; history hrefs are dynamic
      to={to as TanStackTo}
      className={`${pfClass}${selectedClass}${extraClass}`.trim()}
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
