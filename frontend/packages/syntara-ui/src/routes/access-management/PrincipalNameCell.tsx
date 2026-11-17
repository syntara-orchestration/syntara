import { Truncate } from '@patternfly/react-core'

import { LinkCell } from '../../components/table/LinkCell'

import { getPrincipalDetailDestination } from './accessManagementPaths'
import type { RolePrincipalType } from './RoleAssignmentTypes'

type PrincipalNameCellProps = {
  principalType: RolePrincipalType
  principalId: string
  name: string
}

/** Table cell linking a principal name to its Access Management detail page. */
export function PrincipalNameCell({ principalType, principalId, name }: Readonly<PrincipalNameCellProps>) {
  if (!principalId) {
    return <Truncate content={name} />
  }

  return (
    <LinkCell href={getPrincipalDetailDestination(principalType, principalId)}>
      <Truncate content={name} />
    </LinkCell>
  )
}
