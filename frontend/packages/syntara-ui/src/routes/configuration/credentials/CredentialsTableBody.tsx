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
import { RhUiCaretDownIcon, RhUiCaretRightIcon, RhUiEditIcon, RhUiTrashIcon } from '@patternfly/react-icons'
import { ExpandableRowContent, Tbody, Td, Tr } from '@patternfly/react-table'
import { Fragment, useMemo } from 'react'

import { AppRoute } from '../../../app/AppRoute'
import groupedTableStyles from '../../../components/groupedTable.module.css'
import { IconLabel } from '../../../components/IconLabel'
import type { KebabAction } from '../../../components/SynKebabMenu'
import { SynKebabMenu } from '../../../components/SynKebabMenu'
import { LinkCell } from '../../../components/table/LinkCell'
import { UserTimestamp } from '../../../components/table/UserTimestamp'
import { builtinProjectTooltip } from '../../../hooks/permissionUtils'
import type { ProjectRead } from '../../access/types'

import type { Credential, CredentialType } from './credentialConstants'
import { useCredentialPermissions } from './useCredentialPermissions'

/** Total visible columns including expand toggle and actions. */
const COLUMN_COUNT = 9

export type CredentialRowAction = KebabAction

type CredentialRowProps = {
  credential: Credential
  credType: CredentialType | undefined
  rowIndex: number
  isExpanded: boolean
  isBuiltinProject: boolean
  onToggleRow: (id: string) => void
  onEdit: (credential: Credential) => void
  onDelete: (credential: Credential) => void
  onToggleEnabled: (credential: Credential) => void
}

function CredentialRow({
  credential,
  credType,
  rowIndex,
  isExpanded,
  isBuiltinProject,
  onToggleRow,
  onEdit,
  onDelete,
  onToggleEnabled,
}: Readonly<CredentialRowProps>) {
  const permissions = useCredentialPermissions({ resourceProject: credential.project_id })

  const hasDescription = Boolean(credential.description?.trim())

  const actions = useMemo<KebabAction[]>(() => {
    const { isLoading, canUpdate, canDelete, tooltips } = permissions
    const updateTooltip = isLoading || canUpdate ? undefined : { content: tooltips.update }
    const noUpdate = isBuiltinProject ? { content: builtinProjectTooltip('edit this credential') } : updateTooltip
    const deleteTooltip = isLoading || canDelete ? undefined : { content: tooltips.delete }
    const noDelete = isBuiltinProject ? { content: builtinProjectTooltip('delete this credential') } : deleteTooltip
    return [
      {
        key: 'edit',
        title: <IconLabel icon={<RhUiEditIcon />}>Edit credential</IconLabel>,
        isAriaDisabled: isBuiltinProject || isLoading || !canUpdate,
        tooltipProps: noUpdate,
        onClick: () => onEdit(credential),
      },
      { key: 'sep-delete', isSeparator: true },
      {
        key: 'delete',
        title: <IconLabel icon={<RhUiTrashIcon />}>Delete credential</IconLabel>,
        isDanger: true,
        isAriaDisabled: isBuiltinProject || isLoading || !canDelete,
        tooltipProps: noDelete,
        onClick: () => onDelete(credential),
      },
    ]
  }, [permissions, isBuiltinProject, credential, onEdit, onDelete])

  const toggleDisabled = isBuiltinProject || permissions.isLoading || !permissions.canUpdate

  const toggleDisabledTooltip = useMemo(() => {
    if (isBuiltinProject) return builtinProjectTooltip('enable or disable this credential')
    if (permissions.isLoading) return undefined
    return permissions.canUpdate ? undefined : permissions.tooltips.enable
  }, [isBuiltinProject, permissions.isLoading, permissions.canUpdate, permissions.tooltips.enable])

  const toggleSwitch = (
    <Switch
      id={`credential-toggle-${credential.id}`}
      label="Enabled"
      isChecked={credential.enabled}
      isDisabled={toggleDisabled}
      onChange={toggleDisabled ? undefined : () => onToggleEnabled(credential)}
    />
  )

  return (
    <Tbody isExpanded={isExpanded}>
      <Tr isContentExpanded={isExpanded}>
        <Td
          expand={
            hasDescription
              ? {
                  rowIndex,
                  isExpanded,
                  // eslint-disable-next-line @typescript-eslint/no-non-null-assertion -- safe: credentials from the API always have an id; rows without id are excluded by the expandableCredentialIds filter upstream
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
          {toggleDisabledTooltip ? <Tooltip content={toggleDisabledTooltip}>{toggleSwitch}</Tooltip> : toggleSwitch}
        </Td>
        <Td isActionCell onClick={(e) => e.stopPropagation()}>
          <SynKebabMenu actions={actions} aria-label={`Actions for ${credential.name}`} />
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
  onEdit: (credential: Credential) => void
  onDelete: (credential: Credential) => void
  onToggleEnabled: (credential: Credential) => void
  getIsBuiltinProject: (credential: Credential) => boolean
}

export function GroupedCredentialsTableBody({
  groupedCredentials,
  collapsedProjects,
  onToggleProject,
  typeMap,
  expandedRows,
  onToggleRow,
  onEdit,
  onDelete,
  onToggleEnabled,
  getIsBuiltinProject,
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
                  isExpanded={credential.id != null && expandedRows.has(credential.id)}
                  isBuiltinProject={getIsBuiltinProject(credential)}
                  onToggleRow={onToggleRow}
                  onEdit={onEdit}
                  onDelete={onDelete}
                  onToggleEnabled={onToggleEnabled}
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
  onEdit: (credential: Credential) => void
  onDelete: (credential: Credential) => void
  onToggleEnabled: (credential: Credential) => void
  getIsBuiltinProject: (credential: Credential) => boolean
}

export function FlatCredentialsTableBody({
  credentials,
  typeMap,
  expandedRows,
  onToggleRow,
  onEdit,
  onDelete,
  onToggleEnabled,
  getIsBuiltinProject,
}: Readonly<FlatCredentialsTableBodyProps>) {
  return (
    <>
      {credentials.map((credential, rowIndex) => (
        <CredentialRow
          key={credential.id}
          credential={credential}
          credType={typeMap.get(credential.credential_type_id)}
          rowIndex={rowIndex}
          isExpanded={credential.id != null && expandedRows.has(credential.id)}
          isBuiltinProject={getIsBuiltinProject(credential)}
          onToggleRow={onToggleRow}
          onEdit={onEdit}
          onDelete={onDelete}
          onToggleEnabled={onToggleEnabled}
        />
      ))}
    </>
  )
}
