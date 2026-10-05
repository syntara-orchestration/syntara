import { Spinner } from '@patternfly/react-core'
import type { Approval } from '@syntara/contracts'

import { SynPage, SynPageBody } from '../../components/layout/SynPage'
import { SynPageHeader } from '../../components/layout/SynPageHeader'
import { SynEmptyStateAccessDenied } from '../../components/states/SynEmptyStateAccessDenied'
import { SynPageTitle } from '../../components/SynPageTitle'
import { useDocLink } from '../../utils/docs/useDocLink'

import ApprovalsListPanel from './ApprovalsListPanel'
import { useApprovalPermissions } from './useApprovalPermissions'

export type ApprovalWithDetails = Approval & {
  approvalName?: string
  workflowName?: string
  workflowId?: string
  workflowVersion?: number
}

export default function Approvals() {
  const approvalsDocLink = useDocLink('approvals')
  const permissions = useApprovalPermissions()

  if (permissions.isChecking) {
    return (
      <SynPage>
        <SynPageTitle segments={['Approvals']} />
        <SynPageHeader title="Approvals" docLink={approvalsDocLink ?? undefined} />
        <SynPageBody isCentered>
          <Spinner aria-label="Loading approval permissions" />
        </SynPageBody>
      </SynPage>
    )
  }

  if (!permissions.canRead) {
    return (
      <SynPage>
        <SynPageTitle segments={['Approvals']} />
        <SynPageHeader title="Approvals" docLink={approvalsDocLink ?? undefined} />
        <SynPageBody isCentered>
          <SynEmptyStateAccessDenied description="You do not have permission to view approvals. Contact your administrator to request access." />
        </SynPageBody>
      </SynPage>
    )
  }

  return <ApprovalsListPanel approvalsDocLink={approvalsDocLink} />
}
