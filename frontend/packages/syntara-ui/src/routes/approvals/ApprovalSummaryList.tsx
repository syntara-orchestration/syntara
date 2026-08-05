import {
  DescriptionList,
  DescriptionListDescription,
  DescriptionListGroup,
  DescriptionListTerm,
} from '@patternfly/react-core'

import { DateCell } from '../../components/table/DateCell'

type ApprovalSummaryListProps = {
  workflowName: string
  approvalInitiatedAt: string | null | undefined
}

export function ApprovalSummaryList(props: ApprovalSummaryListProps) {
  return (
    <DescriptionList
      isAutoColumnWidths
      columnModifier={{ default: '3Col' }}
      style={{ justifyContent: 'space-between' }}
    >
      <DescriptionListGroup>
        <DescriptionListTerm>Approval type</DescriptionListTerm>
        <DescriptionListDescription>
          Approval step {/** display of step type is hardcoded; multiple approval types are not yet implemented */}
        </DescriptionListDescription>
      </DescriptionListGroup>
      <DescriptionListGroup>
        <DescriptionListTerm>Workflow</DescriptionListTerm>
        <DescriptionListDescription>{props.workflowName}</DescriptionListDescription>
      </DescriptionListGroup>
      <DescriptionListGroup>
        <DescriptionListTerm>Approval initiated</DescriptionListTerm>
        <DescriptionListDescription>
          <DateCell dateString={props.approvalInitiatedAt} />
        </DescriptionListDescription>
      </DescriptionListGroup>
    </DescriptionList>
  )
}
