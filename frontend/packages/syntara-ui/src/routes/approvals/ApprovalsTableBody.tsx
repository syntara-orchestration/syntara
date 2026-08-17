import {
  Checkbox,
  DescriptionList,
  DescriptionListDescription,
  DescriptionListGroup,
  DescriptionListTerm,
  Flex,
  FlexItem,
  Tooltip,
} from '@patternfly/react-core'
import { RhUiCaretDownIcon, RhUiCaretRightIcon } from '@patternfly/react-icons'
import { Tbody, Td, Tr, ExpandableRowContent } from '@patternfly/react-table'
import { Fragment } from 'react'

import groupedTableStyles from '../../components/groupedTable.module.css'
import { DateCell } from '../../components/table/DateCell'
import { LinkCell } from '../../components/table/LinkCell'
import { UserTimestamp } from '../../components/table/UserTimestamp'
import type { ProjectRead } from '../access/types'

import { getNotesLabel, hasExpandableNotes } from './approvalNotes'
import type { ApprovalWithDetails } from './Approvals'
import styles from './ApprovalsTableBody.module.css'
import { ApprovalStatusBadges } from './approvalUtils'
import { buildWorkflowBuilderLink } from './buildWorkflowBuilderLink'
import { getDisabledTooltip } from './getDisabledTooltip'
import { isApprovalSelectable } from './isApprovalSelectable'
import { useCanDecideApproval } from './useCanDecideApproval'

function DecidedCell({ approval }: Readonly<{ approval: ApprovalWithDetails }>) {
  if (!approval.decided_at) {
    return <DateCell dateString={null} />
  }

  return <UserTimestamp user={approval.decided_by} timestamp={approval.decided_at} inline />
}

function SelectCheckboxCell({
  approval,
  rowIndex,
  isPending,
  isSelected,
  canDecideOnThisApproval,
  canDecideBasedOnApproverList,
  isLoadingPermissions,
  isCheckingApproverList,
  onSelectRow,
}: Readonly<{
  approval: ApprovalWithDetails
  rowIndex: number
  isPending: boolean
  isSelected: boolean
  canDecideOnThisApproval: boolean
  canDecideBasedOnApproverList: boolean
  isLoadingPermissions: boolean
  isCheckingApproverList: boolean
  onSelectRow?: (approval: ApprovalWithDetails, checked: boolean) => void
}>) {
  const showDisabledWithTooltip = !isApprovalSelectable(
    approval,
    canDecideOnThisApproval,
    canDecideBasedOnApproverList,
    isLoadingPermissions,
    isCheckingApproverList
  )

  const disabledTooltip = getDisabledTooltip(approval.status ?? '', canDecideOnThisApproval)

  if (showDisabledWithTooltip) {
    return (
      <Td aria-label={`Select row ${rowIndex}`} className={styles.disabledCheckboxCell}>
        <Tooltip content={disabledTooltip}>
          <span>
            <Checkbox
              id={`select-approval-${approval.id}`}
              isChecked={false}
              isDisabled
              aria-label={`Select row ${rowIndex}`}
              onChange={() => undefined}
            />
          </span>
        </Tooltip>
      </Td>
    )
  }

  return (
    <Td
      select={
        isPending
          ? {
              rowIndex,
              onSelect: (_event, isSelecting) => onSelectRow?.(approval, isSelecting),
              isSelected,
              isDisabled: isLoadingPermissions || isCheckingApproverList || !canDecideBasedOnApproverList,
            }
          : undefined
      }
    />
  )
}

function ApprovalRow({
  approval,
  rowIndex,
  isExpanded,
  onToggleRow,
  showSelect = false,
  isSelected = false,
  onSelectRow,
  canDecideOnThisApproval = false,
  isLoadingPermissions = false,
}: Readonly<{
  approval: ApprovalWithDetails
  rowIndex: number
  isExpanded: boolean
  onToggleRow: (id: string) => void
  showSelect?: boolean
  isSelected?: boolean
  onSelectRow?: (approval: ApprovalWithDetails, checked: boolean) => void
  canDecideOnThisApproval?: boolean
  isLoadingPermissions?: boolean
}>) {
  const isPending = approval.status === 'pending'
  const isExpandable = hasExpandableNotes(approval)

  // SECURITY: Client-side check for UX only - disables checkbox for unauthorized users
  // Backend ALWAYS validates and returns 403 via ApprovalService._is_user_authorized_approver()
  const { canDecide: canDecideBasedOnApproverList, isLoading: isCheckingApproverList } = useCanDecideApproval(approval)

  return (
    <Fragment key={approval.id}>
      <Tr isContentExpanded={isExpanded}>
        {showSelect && (
          <SelectCheckboxCell
            approval={approval}
            rowIndex={rowIndex}
            isPending={isPending}
            isSelected={isSelected}
            canDecideOnThisApproval={canDecideOnThisApproval}
            canDecideBasedOnApproverList={canDecideBasedOnApproverList}
            isLoadingPermissions={isLoadingPermissions}
            isCheckingApproverList={isCheckingApproverList}
            onSelectRow={onSelectRow}
          />
        )}
        <Td
          expand={
            isExpandable
              ? {
                  rowIndex,
                  isExpanded,
                  onToggle: () => onToggleRow(approval.id),
                }
              : undefined
          }
        />
        <Td dataLabel="Approval name">
          <LinkCell href={`/executions/${approval.execution_id}?approval=${approval.id}&history=closed`}>
            {approval.approvalName || approval.id}
          </LinkCell>
        </Td>
        <Td dataLabel="Workflow">
          {approval.workflowId ? (
            <LinkCell href={buildWorkflowBuilderLink(approval.workflowId, approval.workflowVersion)}>
              {approval.workflowName || approval.workflowId}
            </LinkCell>
          ) : (
            (approval.workflowName ?? '—')
          )}
        </Td>
        <Td dataLabel="Approval initiated">
          <DateCell dateString={approval.created_at} />
        </Td>
        <Td dataLabel="Actioned on">
          <DecidedCell approval={approval} />
        </Td>
        <Td dataLabel="Status">
          <ApprovalStatusBadges status={approval.status} />
        </Td>
      </Tr>
      {isExpandable && (
        <Tr isExpanded={isExpanded}>
          <Td colSpan={showSelect ? 7 : 6}>
            <ExpandableRowContent>
              <DescriptionList>
                <DescriptionListGroup>
                  <DescriptionListTerm>{getNotesLabel(approval.status)}</DescriptionListTerm>
                  <DescriptionListDescription>{approval.decision_notes}</DescriptionListDescription>
                </DescriptionListGroup>
              </DescriptionList>
            </ExpandableRowContent>
          </Td>
        </Tr>
      )}
    </Fragment>
  )
}

type ProjectGroup = {
  project: ProjectRead | null
  approvals: ApprovalWithDetails[]
}

type GroupedApprovalsTableBodyProps = {
  groupedApprovals: Map<string, ProjectGroup>
  collapsedProjects: Set<string>
  onToggleProject: (projectId: string) => void
  expandedRows: Set<string>
  onToggleRow: (id: string) => void
  showSelect?: boolean
  selectedApprovalIds?: Set<string>
  onSelectRow?: (approval: ApprovalWithDetails, checked: boolean) => void
  approvalPermissions: Map<string, boolean>
  isLoadingPermissions: boolean
}

export function GroupedApprovalsTableBody({
  groupedApprovals,
  collapsedProjects,
  onToggleProject,
  expandedRows,
  onToggleRow,
  showSelect = false,
  selectedApprovalIds,
  onSelectRow,
  approvalPermissions,
  isLoadingPermissions,
}: Readonly<GroupedApprovalsTableBodyProps>) {
  const approvalIndexMap = new Map<string, number>()
  let globalIndex = 0
  for (const { approvals } of groupedApprovals.values()) {
    for (const approval of approvals) {
      approvalIndexMap.set(approval.id, globalIndex++)
    }
  }

  return (
    <>
      {[...groupedApprovals.entries()].map(([projectId, { project, approvals }]) => (
        <Tbody key={projectId}>
          <Tr className={groupedTableStyles.groupHeader} onClick={() => onToggleProject(projectId)}>
            <Td colSpan={showSelect ? 7 : 6}>
              <Flex alignItems={{ default: 'alignItemsCenter' }} gap={{ default: 'gapSm' }}>
                <FlexItem>{collapsedProjects.has(projectId) ? <RhUiCaretRightIcon /> : <RhUiCaretDownIcon />}</FlexItem>
                <FlexItem>
                  <strong>{project?.name ?? (projectId === 'unknown' ? 'No project' : projectId)}</strong>
                </FlexItem>
              </Flex>
            </Td>
          </Tr>
          {!collapsedProjects.has(projectId) &&
            approvals.map((approval) => (
              <ApprovalRow
                key={approval.id}
                approval={approval}
                rowIndex={approvalIndexMap.get(approval.id) ?? 0}
                isExpanded={expandedRows.has(approval.id)}
                onToggleRow={onToggleRow}
                showSelect={showSelect}
                isSelected={selectedApprovalIds?.has(approval.id)}
                onSelectRow={onSelectRow}
                canDecideOnThisApproval={approvalPermissions.get(approval.id) ?? false}
                isLoadingPermissions={isLoadingPermissions}
              />
            ))}
        </Tbody>
      ))}
    </>
  )
}

type FlatApprovalsTableBodyProps = {
  approvals: ApprovalWithDetails[]
  expandedRows: Set<string>
  onToggleRow: (id: string) => void
  showSelect?: boolean
  selectedApprovalIds?: Set<string>
  onSelectRow?: (approval: ApprovalWithDetails, checked: boolean) => void
  approvalPermissions: Map<string, boolean>
  isLoadingPermissions: boolean
}

export function FlatApprovalsTableBody({
  approvals,
  expandedRows,
  onToggleRow,
  showSelect = false,
  selectedApprovalIds,
  onSelectRow,
  approvalPermissions,
  isLoadingPermissions,
}: Readonly<FlatApprovalsTableBodyProps>) {
  return (
    <Tbody>
      {approvals.map((approval, index) => (
        <ApprovalRow
          key={approval.id}
          approval={approval}
          rowIndex={index}
          isExpanded={expandedRows.has(approval.id)}
          onToggleRow={onToggleRow}
          showSelect={showSelect}
          isSelected={selectedApprovalIds?.has(approval.id)}
          onSelectRow={onSelectRow}
          canDecideOnThisApproval={approvalPermissions.get(approval.id) ?? false}
          isLoadingPermissions={isLoadingPermissions}
        />
      ))}
    </Tbody>
  )
}
