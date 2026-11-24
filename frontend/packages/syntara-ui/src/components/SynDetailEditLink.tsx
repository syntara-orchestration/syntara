import { Button } from '@patternfly/react-core'
import { RhUiEditIcon } from '@patternfly/react-icons'
import type { ReactNode } from 'react'

import { TanStackRouterButtonLink } from './SynLink'

type SynDetailEditLinkProps = {
  to: string
  children: ReactNode
  isAriaDisabled?: boolean
  icon?: ReactNode
}

/** Primary-pattern edit control on detail pages: PatternFly button styled anchor to an edit route. */
export function SynDetailEditLink({
  to,
  children,
  isAriaDisabled = false,
  icon = <RhUiEditIcon />,
}: Readonly<SynDetailEditLinkProps>) {
  return (
    <Button
      variant="primary"
      icon={icon}
      component={TanStackRouterButtonLink}
      href={to}
      isAriaDisabled={isAriaDisabled}
    >
      {children}
    </Button>
  )
}
