import type { ReactNode } from 'react'

import type { AppBreadcrumbItem } from '../../app/breadcrumbs/appBreadcrumbItem'
import { SynPage, SynPageBody } from '../../components/layout/SynPage'
import { SynPageHeader } from '../../components/layout/SynPageHeader'
import { SynPanel } from '../../components/layout/SynPanel'
import { SynPageTitle } from '../../components/SynPageTitle'

type DetailPageShellProps = {
  title: string
  children: ReactNode
  breadcrumbs?: readonly AppBreadcrumbItem[]
  docLink?: string
}

/**
 * Shared shell for detail page early-return states (loading, error, not-found).
 * Wraps content in the standard SynPage → SynPageHeader → full-height Panel layout
 * so each detail page does not duplicate the same structure.
 */
export function DetailPageShell({ title, children, breadcrumbs, docLink }: Readonly<DetailPageShellProps>) {
  return (
    <SynPage>
      <SynPageTitle segments={[title]} />
      <SynPageHeader title={title} breadcrumbs={breadcrumbs} docLink={docLink} />
      <SynPageBody>
        <SynPanel isFullHeight>{children}</SynPanel>
      </SynPageBody>
    </SynPage>
  )
}
