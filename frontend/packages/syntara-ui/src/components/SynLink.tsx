import { Button } from '@patternfly/react-core'
import { Link as TanStackLink } from '@tanstack/react-router'
import type { ComponentProps, ReactNode, Ref } from 'react'

import type { AccessManagementDetailDestination } from '../app/typed-route-destinations'

type ButtonOnClick = ComponentProps<typeof Button>['onClick']

type RouterLinkProps = React.AnchorHTMLAttributes<HTMLAnchorElement> & {
  routeOptions?: AccessManagementDetailDestination
}

/** Bridge PatternFly Button hrefs and typed route options to TanStack Router. */
export function TanStackRouterButtonLink({ href, routeOptions, children, ...rest }: RouterLinkProps) {
  if (routeOptions) {
    return (
      <TanStackLink {...routeOptions} {...rest}>
        {children}
      </TanStackLink>
    )
  }

  return (
    <TanStackLink to={href ?? '/'} {...(rest as Omit<ComponentProps<typeof TanStackLink>, 'to' | 'children'>)}>
      {children}
    </TanStackLink>
  )
}

type SynLinkProps = {
  /** Route path or typed Access Management detail destination. */
  to: string | AccessManagementDetailDestination
  children: ReactNode
  className?: string
  onClick?: ButtonOnClick
  ref?: Ref<HTMLAnchorElement>
}

/**
 * Application-level link that renders a PatternFly inline link button
 * wired to TanStack Router for client-side navigation.
 */
export function SynLink({ to, children, className, onClick, ref }: Readonly<SynLinkProps>) {
  const linkTarget = typeof to === 'string' ? { href: to } : { href: to.to, routeOptions: to }

  return (
    <Button
      ref={ref}
      variant="link"
      isInline
      component={TanStackRouterButtonLink}
      {...linkTarget}
      className={className}
      onClick={onClick}
    >
      {children}
    </Button>
  )
}
