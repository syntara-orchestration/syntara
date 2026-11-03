import { Breadcrumb, BreadcrumbItem, Truncate } from '@patternfly/react-core'
import type { BreadcrumbItemRenderArgs, TooltipProps } from '@patternfly/react-core'
import { Link } from '@tanstack/react-router'
import { useSyncExternalStore } from 'react'

import type { AppBreadcrumbItem } from '../../app/breadcrumbs/appBreadcrumbItem'

import styles from './SynPageBreadcrumbs.module.css'
import { SynPageBreadcrumbsCollapsedMiddle } from './SynPageBreadcrumbsCollapsedMiddle'

export type { AppBreadcrumbItem }

const breadcrumbTruncateTooltipProps = {
  enableFlip: true,
  maxWidth: 'min(100vw - 2rem, 24rem)',
  position: 'bottom',
} satisfies Omit<TooltipProps, 'content'>

function BreadcrumbTruncatedLabel({
  label,
  testId = 'breadcrumb-truncated-label',
}: Readonly<{
  label: string
  testId?: string
}>) {
  return (
    <Truncate
      content={label}
      className={styles.truncatedLabel}
      data-testid={testId}
      tooltipProps={breadcrumbTruncateTooltipProps}
    />
  )
}

function renderBreadcrumbLink(href: string, label: string) {
  return ({ className, ariaCurrent }: BreadcrumbItemRenderArgs) => (
    // TanStack Router expects literal route strings; breadcrumb hrefs are dynamic
    <Link to={href} className={`${className ?? ''} ${styles.segmentLink}`} aria-current={ariaCurrent}>
      <BreadcrumbTruncatedLabel label={label} />
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

function BreadcrumbCurrentLabel({ label }: Readonly<{ label: string }>) {
  return <BreadcrumbTruncatedLabel label={label} testId="breadcrumb-current-segment" />
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
    <Breadcrumb aria-label="Breadcrumb" className={styles.breadcrumb}>
      {collapseMiddle ? (
        <>
          {first.href ? (
            <BreadcrumbItem render={renderBreadcrumbLink(first.href, first.label)} />
          ) : (
            <BreadcrumbItem isActive>{first.label}</BreadcrumbItem>
          )}
          <SynPageBreadcrumbsCollapsedMiddle middleItems={middle} />
          <BreadcrumbItem isActive>
            <BreadcrumbCurrentLabel label={last.label} />
          </BreadcrumbItem>
        </>
      ) : (
        items.map((item, index) => {
          const isLast = index === lastIndex
          const itemKey = item.href ?? `current:${item.label}`
          if (isLast) {
            return (
              <BreadcrumbItem key={itemKey} isActive>
                <BreadcrumbCurrentLabel label={item.label} />
              </BreadcrumbItem>
            )
          }
          if (item.href) {
            return <BreadcrumbItem key={item.href} render={renderBreadcrumbLink(item.href, item.label)} />
          }
          return (
            <BreadcrumbItem key={itemKey} isActive>
              <BreadcrumbTruncatedLabel label={item.label} />
            </BreadcrumbItem>
          )
        })
      )}
    </Breadcrumb>
  )
}
