import { Button } from '@patternfly/react-core'

import { SynLink } from '../SynLink'

type SynFormCancelButtonProps = {
  /** When set, renders a router link for navigation back to a list or detail route. */
  to?: string
  /** Used when there is no stable route target (for example closing an editor panel). */
  onClick?: () => void
  isDisabled?: boolean
}

/**
 * Cancel control for full-page forms and wizard footers.
 * Uses PatternFly link styling; prefers {@link SynLink} when `to` is set.
 */
export function SynFormCancelButton({ to, onClick, isDisabled }: Readonly<SynFormCancelButtonProps>) {
  if (to) {
    if (isDisabled) {
      return (
        <Button variant="link" isAriaDisabled>
          Cancel
        </Button>
      )
    }
    return <SynLink to={to}>Cancel</SynLink>
  }

  return (
    <Button variant="link" onClick={isDisabled ? undefined : onClick} isAriaDisabled={isDisabled}>
      Cancel
    </Button>
  )
}
