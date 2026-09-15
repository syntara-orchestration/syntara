import { Breadcrumb, BreadcrumbItem } from '@patternfly/react-core'
import type { BreadcrumbItemRenderArgs } from '@patternfly/react-core'
import { Link } from '@tanstack/react-router'
import type { ComponentProps } from 'react'
import { useSyncExternalStore } from 'react'

import type { AppBreadcrumbItem } from '../../app/breadcrumbs/appBreadcrumbItem'

import { SynPageBreadcrumbsCollapsedMiddle } from './SynPageBreadcrumbsCollapsedMiddle'

export type { AppBreadcrumbItem }

type TanStackTo = ComponentProps<typeof Link>['to']

function renderBreadcrumbLink(href: string, label: string) {
  return ({ className, ariaCurrent }: BreadcrumbItemRenderArgs) => (
    // TanStack Router expects literal route strings; breadcrumb hrefs are dynamic
    <Link to={href as TanStackTo} className={className} aria-current={ariaCurrent}>
      {label}
    </Link>
  )
}

const NARROW_MEDIA_QUERY = '(max-width: 768px)'

function subscribeNarrowMedia(callback: () => void) {
  const mq = globalThis.window?.matchMedia?.(NARROW_MEDIA_QUERY)
  if (!mq) {
    return () => {}
  }
  mq.addEventListener('change', callback)
  return () => mq.removeEventListener('change', callback)
}

function getNarrowMediaSnapshot() {
  return globalThis.window?.matchMedia?.(NARROW_MEDIA_QUERY).matches ?? false
}

function getNarrowMediaServerSnapshot() {
  return false
}

function useNarrowViewportForBreadcrumb() {
  return useSyncExternalStore(subscribeNarrowMedia, getNarrowMediaSnapshot, getNarrowMediaServerSnapshot)
}

type SynPageBreadcrumbsProps = Readonly<{
  /** Ordered breadcrumb segments. Requires at least two items to render. */
  items: readonly AppBreadcrumbItem[]
}>

/** Breadcrumb trail where parent items are links and the last item is the current page. On narrow viewports, two or more middle segments collapse into a dropdown. */
export function SynPageBreadcrumbs(props: SynPageBreadcrumbsProps) {
  const { items } = props
  const isNarrow = useNarrowViewportForBreadcrumb()

  if (items.length < 2) {
    return null
  }

  const lastIndex = items.length - 1
  const first = items[0]
  const last = items[lastIndex]
  const middle = items.slice(1, lastIndex)
  const collapseMiddle = isNarrow && middle.length >= 2

  return (
    <Breadcrumb aria-label="Breadcrumb">
      {collapseMiddle ? (
        <>
          {first.href ? (
            <BreadcrumbItem render={renderBreadcrumbLink(first.href, first.label)} />
          ) : (
            <BreadcrumbItem isActive>{first.label}</BreadcrumbItem>
          )}
          <SynPageBreadcrumbsCollapsedMiddle middleItems={middle} />
          <BreadcrumbItem isActive>{last.label}</BreadcrumbItem>
        </>
      ) : (
        items.map((item, index) => {
          const isLast = index === lastIndex
          const itemKey = item.href ?? `current:${item.label}`
          if (isLast) {
            return (
              <BreadcrumbItem key={itemKey} isActive>
                {item.label}
              </BreadcrumbItem>
            )
          }
          if (item.href) {
            return <BreadcrumbItem key={item.href} render={renderBreadcrumbLink(item.href, item.label)} />
          }
          return (
            <BreadcrumbItem key={itemKey} isActive>
              {item.label}
            </BreadcrumbItem>
          )
        })
      )}
    </Breadcrumb>
  )
}
