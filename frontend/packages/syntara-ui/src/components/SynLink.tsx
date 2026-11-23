import { Button } from '@patternfly/react-core'
import { Link as TanStackLink } from '@tanstack/react-router'
import type { ComponentProps, ReactNode, Ref } from 'react'

type ButtonOnClick = ComponentProps<typeof Button>['onClick']

type RouterLinkProps = React.AnchorHTMLAttributes<HTMLAnchorElement>

/** Bridge PatternFly Button `href` to TanStack Router `to` for client-side navigation. */
export function TanStackRouterButtonLink({ href, children, ...rest }: RouterLinkProps) {
  return (
    <TanStackLink to={href ?? '/'} {...(rest as Omit<ComponentProps<typeof TanStackLink>, 'to' | 'children'>)}>
      {children}
    </TanStackLink>
  )
}

type SynLinkProps = {
  /** Route path to navigate to on click. */
  to: string
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
  return (
    <Button
      ref={ref}
      variant="link"
      isInline
      component={TanStackRouterButtonLink}
      href={to}
      className={className}
      onClick={onClick}
    >
      {children}
    </Button>
  )
}
