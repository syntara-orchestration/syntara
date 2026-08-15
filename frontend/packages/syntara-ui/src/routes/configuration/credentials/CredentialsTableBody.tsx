import {
  DescriptionList,
  DescriptionListDescription,
  DescriptionListGroup,
  DescriptionListTerm,
  Flex,
  FlexItem,
  Switch,
  Tooltip,
  Truncate,
} from '@patternfly/react-core'
import { RhUiCaretDownIcon, RhUiCaretRightIcon } from '@patternfly/react-icons'
import { ExpandableRowContent, Tbody, Td, Tr } from '@patternfly/react-table'
import { Fragment } from 'react'

import { AppRoute } from '../../../app/AppRoute'
import groupedTableStyles from '../../../components/groupedTable.module.css'
import type { KebabAction } from '../../../components/NxKebabMenu'
import { NxKebabMenu } from '../../../components/NxKebabMenu'
import { LinkCell } from '../../../components/table/LinkCell'
import { UserTimestamp } from '../../../components/table/UserTimestamp'
import type { ProjectRead } from '../../access/types'

import type { Credential, CredentialType } from './credentialConstants'

/** Total visible columns including expand toggle and actions. */
const COLUMN_COUNT = 9

export type CredentialRowAction = KebabAction

type CredentialRowProps = {
  credential: Credential
  credType: CredentialType | undefined
  rowIndex: number
  isExpanded: boolean
  onToggleRow: (id: string) => void
  getRowActions: (credential: Credential) => CredentialRowAction[]
  onToggleEnabled: (credential: Credential) => void
  getToggleDisabledTooltip?: (credential: Credential) => string | undefined
}

function CredentialRow({
  credential,
  credType,
  rowIndex,
  isExpanded,
  onToggleRow,
  getRowActions,
  onToggleEnabled,
  getToggleDisabledTooltip,
}: Readonly<CredentialRowProps>) {
  const hasDescription = Boolean(credential.description?.trim())
  const actions = getRowActions(credential)
  const toggleDisabledTooltip = getToggleDisabledTooltip?.(credential)

  return (
    <Tbody isExpanded={isExpanded}>
      <Tr isContentExpanded={isExpanded}>
        <Td
          expand={
            hasDescription
              ? {
                  rowIndex,
                  isExpanded,
                  onToggle: () => onToggleRow(credential.id!),
                }
              : undefined
          }
        />
        <Td dataLabel="Name">
          <LinkCell href={AppRoute.Configuration.Credentials.Detail.replace(':credentialId', credential.id ?? '')}>
            <Truncate content={credential.name} />
          </LinkCell>
        </Td>
        <Td dataLabel="Type">{credType?.name ?? '—'}</Td>
        <Td dataLabel="Workflows">
          {credential.workflow_count != null && credential.workflow_count > 0 ? credential.workflow_count : '—'}
        </Td>
        <Td dataLabel="Integrations">
          {credential.integration_count != null && credential.integration_count > 0
            ? credential.integration_count
            : '—'}
        </Td>
        <Td dataLabel="Created">
          <UserTimestamp user={credential.created_by} timestamp={credential.created_at} inline />
        </Td>
        <Td dataLabel="Last modified">
          <UserTimestamp user={credential.updated_by} timestamp={credential.updated_at} inline />
        </Td>
        <Td dataLabel="State" onClick={(e) => e.stopPropagation()}>
          {toggleDisabledTooltip ? (
            <Tooltip content={toggleDisabledTooltip}>
              <Switch
                id={`credential-toggle-${credential.id}`}
                label="Enabled"
                isChecked={credential.enabled}
                isDisabled
              />
            </Tooltip>
          ) : (
            <Switch
              id={`credential-toggle-${credential.id}`}
              label="Enabled"
              isChecked={credential.enabled}
              onChange={() => onToggleEnabled(credential)}
            />
          )}
        </Td>
        <Td isActionCell onClick={(e) => e.stopPropagation()}>
          <NxKebabMenu actions={actions} aria-label={`Actions for ${credential.name}`} />
        </Td>
      </Tr>
      {hasDescription && (
        <Tr isExpanded={isExpanded}>
          <Td colSpan={COLUMN_COUNT}>
            <ExpandableRowContent>
              <DescriptionList>
                <DescriptionListGroup>
                  <DescriptionListTerm>Description</DescriptionListTerm>
                  <DescriptionListDescription>{credential.description}</DescriptionListDescription>
                </DescriptionListGroup>
              </DescriptionList>
            </ExpandableRowContent>
          </Td>
        </Tr>
      )}
    </Tbody>
  )
}

type ProjectGroup = {
  project: ProjectRead | null
  credentials: Credential[]
}

type GroupedCredentialsTableBodyProps = {
  groupedCredentials: Map<string, ProjectGroup>
  collapsedProjects: Set<string>
  onToggleProject: (projectId: string) => void
  typeMap: Map<string, CredentialType>
  expandedRows: Set<string>
  onToggleRow: (id: string) => void
  getRowActions: (credential: Credential) => CredentialRowAction[]
  onToggleEnabled: (credential: Credential) => void
  getToggleDisabledTooltip?: (credential: Credential) => string | undefined
}

export function GroupedCredentialsTableBody({
  groupedCredentials,
  collapsedProjects,
  onToggleProject,
  typeMap,
  expandedRows,
  onToggleRow,
  getRowActions,
  onToggleEnabled,
  getToggleDisabledTooltip,
}: Readonly<GroupedCredentialsTableBodyProps>) {
  const credentialIndexMap = new Map<string, number>()
  let globalIndex = 0
  for (const { credentials } of groupedCredentials.values()) {
    for (const credential of credentials) {
      if (credential.id) credentialIndexMap.set(credential.id, globalIndex++)
    }
  }

  return (
    <>
      {[...groupedCredentials.entries()].map(([projectId, { project, credentials }]) => {
        const isCollapsed = collapsedProjects.has(projectId)
        return (
          <Fragment key={projectId}>
            <Tbody>
              <Tr className={groupedTableStyles.groupHeader} onClick={() => onToggleProject(projectId)}>
                <Td colSpan={COLUMN_COUNT}>
                  <Flex alignItems={{ default: 'alignItemsCenter' }} gap={{ default: 'gapSm' }}>
                    <FlexItem>{isCollapsed ? <RhUiCaretRightIcon /> : <RhUiCaretDownIcon />}</FlexItem>
                    <FlexItem>
                      <strong>{project?.name ?? (projectId === 'unknown' ? 'No project' : projectId)}</strong>
                    </FlexItem>
                  </Flex>
                </Td>
              </Tr>
            </Tbody>
            {!isCollapsed &&
              credentials.map((credential) => (
                <CredentialRow
                  key={credential.id}
                  credential={credential}
                  credType={typeMap.get(credential.credential_type_id)}
                  rowIndex={(credential.id ? credentialIndexMap.get(credential.id) : undefined) ?? 0}
                  isExpanded={expandedRows.has(credential.id!)}
                  onToggleRow={onToggleRow}
                  getRowActions={getRowActions}
                  onToggleEnabled={onToggleEnabled}
                  getToggleDisabledTooltip={getToggleDisabledTooltip}
                />
              ))}
          </Fragment>
        )
      })}
    </>
  )
}

type FlatCredentialsTableBodyProps = {
  credentials: Credential[]
  typeMap: Map<string, CredentialType>
  expandedRows: Set<string>
  onToggleRow: (id: string) => void
  getRowActions: (credential: Credential) => CredentialRowAction[]
  onToggleEnabled: (credential: Credential) => void
  getToggleDisabledTooltip?: (credential: Credential) => string | undefined
}

export function FlatCredentialsTableBody({
  credentials,
  typeMap,
  expandedRows,
  onToggleRow,
  getRowActions,
  onToggleEnabled,
  getToggleDisabledTooltip,
}: Readonly<FlatCredentialsTableBodyProps>) {
  return (
    <>
      {credentials.map((credential, rowIndex) => (
        <CredentialRow
          key={credential.id}
          credential={credential}
          credType={typeMap.get(credential.credential_type_id)}
          rowIndex={rowIndex}
          isExpanded={expandedRows.has(credential.id!)}
          onToggleRow={onToggleRow}
          getRowActions={getRowActions}
          onToggleEnabled={onToggleEnabled}
          getToggleDisabledTooltip={getToggleDisabledTooltip}
        />
      ))}
    </>
  )
}
