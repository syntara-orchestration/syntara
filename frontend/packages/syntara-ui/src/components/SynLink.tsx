import { Link } from '@tanstack/react-router'
import type { ComponentProps, ReactNode, Ref } from 'react'

import type { AppRouteNavigationOptions } from '../app/routeNavigationOptions'

type LinkOnClick = ComponentProps<typeof Link>['onClick']

type SynLinkProps = {
  /** Validated TanStack destination, including any required params and search state. */
  options: AppRouteNavigationOptions
  children: ReactNode
  className?: string
  onClick?: LinkOnClick
  ref?: Ref<HTMLAnchorElement>
}

/**
 * Application-level link that renders a PatternFly inline link button
 * wired to TanStack Router for client-side navigation.
 */
export function SynLink({ options, children, className, onClick, ref }: Readonly<SynLinkProps>) {
  const classNames = ['pf-v6-c-button', 'pf-m-link', 'pf-m-inline', className].filter(Boolean).join(' ')
  return (
    <Link {...options} ref={ref} className={classNames} onClick={onClick}>
      {children}
    </Link>
  )
}
