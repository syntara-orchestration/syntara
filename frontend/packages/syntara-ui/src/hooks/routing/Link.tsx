import { Link as TanStackLink } from '@tanstack/react-router'
import { type ComponentProps } from 'react'

type LinkProps = React.AnchorHTMLAttributes<HTMLAnchorElement> & {
  href: string
}

/**
 * @deprecated Use `Link` from `@tanstack/react-router` directly.
 */
export function Link({ href, children, ...rest }: Readonly<LinkProps>) {
  return (
    <TanStackLink to={href} {...(rest as Omit<ComponentProps<typeof TanStackLink>, 'to' | 'children'>)}>
      {children}
    </TanStackLink>
  )
}
