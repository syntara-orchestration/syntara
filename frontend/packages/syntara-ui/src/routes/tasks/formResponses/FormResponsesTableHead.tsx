import { Thead, Th, Tr } from '@patternfly/react-table'
import type { ThProps } from '@patternfly/react-table'

export type FormResponsesTableHeadProps = {
  getSortParams: (columnField: string) => ThProps['sort']
  allRowsExpanded: boolean
  collapseAllAriaLabel: string
  onCollapseAll: (event: unknown, rowIndex: number, isOpen: boolean) => void
}

export function FormResponsesTableHead(props: Readonly<FormResponsesTableHeadProps>) {
  const { getSortParams, allRowsExpanded, collapseAllAriaLabel, onCollapseAll } = props

  return (
    <Thead>
      <Tr>
        <Th
          expand={{
            areAllExpanded: !allRowsExpanded,
            collapseAllAriaLabel,
            onToggle: onCollapseAll,
          }}
          aria-label="Row expansion"
        />
        <Th modifier="nowrap" sort={getSortParams('name')}>
          Name
        </Th>
        <Th modifier="nowrap" sort={getSortParams('workflow_name')}>
          Workflow
        </Th>
        <Th modifier="nowrap" sort={getSortParams('created_at')}>
          Initiated
        </Th>
        <Th modifier="nowrap" sort={getSortParams('responded_at')}>
          Actioned on
        </Th>
        <Th modifier="nowrap" sort={getSortParams('status')}>
          Status
        </Th>
      </Tr>
    </Thead>
  )
}
