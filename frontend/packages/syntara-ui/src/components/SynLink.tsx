import { Button } from '@patternfly/react-core'
import { Link as TanStackLink } from '@tanstack/react-router'
import type { ComponentProps, ReactNode, Ref } from 'react'

type ButtonOnClick = ComponentProps<typeof Button>['onClick']
type ButtonIcon = ComponentProps<typeof Button>['icon']
type ButtonVariant = ComponentProps<typeof Button>['variant']

type RouterLinkProps = React.AnchorHTMLAttributes<HTMLAnchorElement>

/** Bridge PF Button's `href` convention to TanStack Router's `to` prop. */
function RouterLink({ href, children, ...rest }: RouterLinkProps) {
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
  variant?: ButtonVariant
  icon?: ButtonIcon
  className?: string
  onClick?: ButtonOnClick
  ref?: Ref<HTMLAnchorElement>
}

/**
 * Application-level route link styled with PatternFly. It defaults to an inline
 * link and supports button variants for prominent navigation actions.
 */
export function SynLink({ to, children, variant = 'link', icon, className, onClick, ref }: Readonly<SynLinkProps>) {
  return (
    <Button
      ref={ref}
      variant={variant}
      isInline={variant === 'link'}
      icon={icon}
      component={RouterLink}
      href={to}
      className={className}
      onClick={onClick}
    >
      {children}
    </Button>
  )
}
