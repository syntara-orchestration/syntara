import { Button, StackItem } from '@patternfly/react-core'
import { RhUiEditIcon, RhUiTrashIcon } from '@patternfly/react-icons'
import { Th, Thead, Tr } from '@patternfly/react-table'
import { useCallback, useMemo, useState } from 'react'

import { credentialsClient } from '../../../client'
import { DisabledWithTooltip } from '../../../components/DisabledWithTooltip'
import { FilterBar } from '../../../components/filters/FilterBar'
import { IconLabel } from '../../../components/IconLabel'
import { SynPage, SynPageBody } from '../../../components/layout/SynPage'
import { SynPageHeader } from '../../../components/layout/SynPageHeader'
import { SynPanel } from '../../../components/layout/SynPanel'
import { SynPanelContentStack } from '../../../components/layout/SynPanelContentStack'
import { SynEmptyStateFilter } from '../../../components/states/SynEmptyStateFilter'
import { useQueryState } from '../../../components/states/useQueryState'
import { SynPageTitle } from '../../../components/SynPageTitle'
import { SynScrollableTableContainer } from '../../../components/table/SynScrollableTableContainer'
import { builtinProjectTooltip } from '../../../hooks/permissionUtils'
import { useCursorPagination, useCursorReset } from '../../../hooks/useCursorPagination'
import { useDeleteAction } from '../../../hooks/useDeleteAction'
import { useProjectSelector } from '../../../hooks/useProjectSelector'
import { useProjectsForGrouping } from '../../../hooks/useProjectsForGrouping'
import { useTableSort } from '../../../hooks/useTableSort'
import { useAlerts } from '../../../providers/alerts'
import type { FilterFieldDefinition } from '../../../types/filters'
import { getErrorMessage } from '../../../utils/apiErrors'
import { detachPromise } from '../../../utils/detachPromise'
import { useDocLink } from '../../../utils/docs/useDocLink'

import type { Credential, CredentialType } from './credentialConstants'
import { CredentialEmptyState } from './CredentialEmptyState'
import { getCredentialNameFilterDefinition } from './credentialFilters'
import { FlatCredentialsTableBody, GroupedCredentialsTableBody, type CredentialRowAction } from './CredentialsTableBody'
import { DeleteCredentialDialog } from './DeleteCredentialDialog'
import { DisableCredentialDialog } from './DisableCredentialDialog'
import { CredentialFormModal } from './form/CredentialFormModal'
import { useCredentialPermissions } from './useCredentialPermissions'
import { useDeleteCredentialState } from './useDeleteCredentialState'
import { useDisableCredentialState } from './useDisableCredentialState'
import { useOptimisticCredentialEnabled } from './useOptimisticCredentialEnabled'

const SORT_FIELDS: Record<number, string> = {
  0: 'name',
  3: 'created_at',
  4: 'updated_at',
}

function buildCredentialRowActions(
  credential: Credential,
  permissions: ReturnType<typeof useCredentialPermissions>,
  isBuiltinProject: boolean,
  callbacks: {
    onEdit: (credential: Credential) => void
    onDelete: (credential: Credential) => void
  }
): CredentialRowAction[] {
  const updatePermissionTooltip = permissions.canUpdate ? undefined : { content: permissions.tooltips.update }
  const noUpdate = isBuiltinProject
    ? { content: builtinProjectTooltip('edit this credential') }
    : updatePermissionTooltip
  const deletePermissionTooltip = permissions.canDelete ? undefined : { content: permissions.tooltips.delete }
  const noDelete = isBuiltinProject
    ? { content: builtinProjectTooltip('delete this credential') }
    : deletePermissionTooltip
  return [
    {
      key: 'edit',
      title: <IconLabel icon={<RhUiEditIcon />}>Edit credential</IconLabel>,
      isAriaDisabled: isBuiltinProject || !permissions.canUpdate,
      tooltipProps: noUpdate,
      onClick: () => callbacks.onEdit(credential),
    },
    { key: 'sep-delete', isSeparator: true },
    {
      key: 'delete',
      title: <IconLabel icon={<RhUiTrashIcon />}>Delete credential</IconLabel>,
      isDanger: true,
      isAriaDisabled: isBuiltinProject || !permissions.canDelete,
      tooltipProps: noDelete,
      onClick: () => callbacks.onDelete(credential),
    },
  ]
}

type CredentialPageToolbarProps = {
  permissions: ReturnType<typeof useCredentialPermissions>
  isBuiltinProject: boolean
  onCreateClick: () => void
}

function CredentialPageToolbar({ permissions, isBuiltinProject, onCreateClick }: Readonly<CredentialPageToolbarProps>) {
  const canCreate = permissions.canCreate && !isBuiltinProject
  const tooltip = isBuiltinProject ? builtinProjectTooltip('create a credential') : permissions.tooltips.create
  return (
    <DisabledWithTooltip isDisabled={!canCreate} content={tooltip}>
      <Button variant="primary" isAriaDisabled={!canCreate} onClick={onCreateClick}>
        Create credential
      </Button>
    </DisabledWithTooltip>
  )
}

// eslint-disable-next-line max-lines-per-function, sonarjs/cognitive-complexity -- pre-existing complexity
export default function Credentials() {
  const credentialsDocLink = useDocLink('credentials')
  const { showAlert } = useAlerts()
  const { selectedProject, isAllProjects, projects, ProjectSelector } = useProjectSelector()
  const projectsForGrouping = useProjectsForGrouping(projects, isAllProjects)
  const projectsById = useMemo(() => new Map(projectsForGrouping.map((p) => [p.id, p])), [projectsForGrouping])
  const permissions = useCredentialPermissions()
  const isBuiltinSelected = !!selectedProject?.is_builtin

  const {
    cursor,
    filters,
    hasActiveFilters,
    queryParams,
    handleFilterChange,
    handleClearAllFilters,
    resetPagination,
    getFooterProps,
  } = useCursorPagination({
    extraParams: selectedProject?.id ? { project_id: selectedProject.id } : undefined,
  })

  // UI state
  const [createModalOpen, setCreateModalOpen] = useState(false)
  const [credentialToEdit, setCredentialToEdit] = useState<Credential | null>(null)
  const {
    credentialToDelete,
    affectedWorkflows: deleteAffectedWorkflows,
    workflowsFetchError: deleteWorkflowsFetchError,
    isLoadingWorkflows: deleteIsLoadingWorkflows,
    affectedIntegrations: deleteAffectedIntegrations,
    integrationsFetchError: deleteIntegrationsFetchError,
    isLoadingIntegrations: deleteIsLoadingIntegrations,
    openDeleteDialog,
    closeDeleteDialog,
  } = useDeleteCredentialState()
  const filterFieldDefinitions = useMemo<FilterFieldDefinition[]>(() => [getCredentialNameFilterDefinition()], [])

  // Sorting - default to newest first (column 3 = created_at, descending)
  const { activeSortIndex, sortDirection, getSortParams } = useTableSort({
    initialSortIndex: 3,
    initialDirection: 'desc',
    onSortChange: resetPagination,
  })

  const finalQueryParams = useMemo(() => {
    const field = SORT_FIELDS[activeSortIndex] ?? 'created_at'
    const sort = sortDirection === 'desc' ? `-${field}` : field
    return { ...queryParams, sort }
  }, [queryParams, activeSortIndex, sortDirection])

  // Fetch credentials
  const query = credentialsClient.useQuery('get', '/credentials', { params: { query: finalQueryParams } })
  const serverCredentials = useMemo(() => query.data?.resources ?? [], [query.data?.resources])

  useCursorReset(serverCredentials.length, hasActiveFilters, cursor, query.isFetching, resetPagination)

  // Fetch credential types for type name lookup
  const typesQuery = credentialsClient.useQuery('get', '/credential_types')
  const typeMap = useMemo(() => {
    const map = new Map<string, CredentialType>()
    for (const t of typesQuery.data?.resources ?? []) {
      map.set(t.id!, t)
    }
    return map
  }, [typesQuery.data])

  // Expandable row state
  const [expandedRows, setExpandedRows] = useState<Set<string>>(new Set())

  // Mutations (patch uses mutateAsync so enable/disable can await inside a useOptimistic Action)
  const { mutateAsync: patchCredential, isPending: isPatchPending } = credentialsClient.useMutation(
    'patch',
    '/credentials/{credential_id}'
  )
  const { mutate: deleteCredential, isPending: isDeletePending } = credentialsClient.useMutation(
    'delete',
    '/credentials/{credential_id}'
  )

  const handleEnabledMutationSuccess = useCallback(() => query.refetch(), [query])
  const handleEnabledMutationError = useCallback(
    (title: string, error: unknown) => {
      showAlert({
        title,
        description: getErrorMessage(error),
        variant: 'danger',
        autoDismiss: true,
      })
    },
    [showAlert]
  )

  const { credentials, setCredentialEnabled } = useOptimisticCredentialEnabled({
    credentials: serverCredentials,
    patchCredential,
    onSuccess: handleEnabledMutationSuccess,
    onError: handleEnabledMutationError,
  })

  const expandableCredentialIds = useMemo(
    () => credentials.filter((c) => Boolean(c.description?.trim())).map((c) => c.id!),
    [credentials]
  )

  const areAllExpanded = useMemo(
    () => expandableCredentialIds.length > 0 && expandableCredentialIds.every((id) => expandedRows.has(id)),
    [expandableCredentialIds, expandedRows]
  )

  const handleToggleRow = useCallback((credentialId: string) => {
    setExpandedRows((prev) => {
      const next = new Set(prev)
      if (next.has(credentialId)) {
        next.delete(credentialId)
      } else {
        next.add(credentialId)
      }
      return next
    })
  }, [])

  const handleToggleAllRows = useCallback(() => {
    if (areAllExpanded) {
      setExpandedRows(new Set())
    } else {
      setExpandedRows(new Set(expandableCredentialIds))
    }
  }, [areAllExpanded, expandableCredentialIds])

  // Group credentials by project when viewing all projects
  const [collapsedProjects, setCollapsedProjects] = useState<Set<string>>(new Set())

  const groupedCredentials = useMemo(() => {
    if (!isAllProjects) return null
    const groups = new Map<
      string,
      { project: (typeof projectsForGrouping)[number] | null; credentials: Credential[] }
    >()
    for (const credential of credentials) {
      const projectId = credential.project_id ?? 'unknown'
      if (!groups.has(projectId)) {
        groups.set(projectId, {
          project: projectsById.get(projectId) ?? null,
          credentials: [],
        })
      }
      groups.get(projectId)!.credentials.push(credential)
    }
    return groups
  }, [credentials, projectsById, isAllProjects])

  const toggleProjectCollapsed = (projectId: string) => {
    setCollapsedProjects((prev) => {
      const next = new Set(prev)
      if (next.has(projectId)) {
        next.delete(projectId)
      } else {
        next.add(projectId)
      }
      return next
    })
  }

  // Disable credential dialog state
  const {
    credentialToDisable,
    affectedWorkflows,
    workflowsFetchError,
    isLoadingWorkflows: disableIsLoadingWorkflows,
    affectedIntegrations: disableAffectedIntegrations,
    integrationsFetchError: disableIntegrationsFetchError,
    isLoadingIntegrations: disableIsLoadingIntegrations,
    openDisableDialog,
    closeDisableDialog,
  } = useDisableCredentialState()

  function handleToggleEnabled(credential: Credential) {
    if (credential.enabled) {
      openDisableDialog(credential)
    } else {
      setCredentialEnabled(credential, true)
    }
  }

  function handleConfirmDisable() {
    if (!credentialToDisable) return
    const target = credentialToDisable
    closeDisableDialog()
    setCredentialEnabled(target, false)
  }

  const handleConfirmDelete = useDeleteAction<Credential, { params: { path: { credential_id: string } } }>({
    deleteFn: (params, callbacks) => deleteCredential(params, callbacks),
    buildParams: (cred) => ({ params: { path: { credential_id: cred.id! } } }),
    entityLabel: 'credential',
    getItemName: (cred) => cred.name,
    onSuccess: () => detachPromise(query.refetch()),
    onSettled: closeDeleteDialog,
  })

  const permissionToggleTooltip = permissions.canUpdate ? undefined : permissions.tooltips.enable
  const getToggleDisabledTooltip = (credential: Credential): string | undefined => {
    const isBuiltinProject = !!selectedProject?.is_builtin || !!projectsById.get(credential.project_id)?.is_builtin
    if (isBuiltinProject) return builtinProjectTooltip('enable or disable this credential')
    return permissionToggleTooltip
  }

  const getRowActions = (credential: Credential) => {
    const isBuiltinProject = !!selectedProject?.is_builtin || !!projectsById.get(credential.project_id)?.is_builtin
    return buildCredentialRowActions(credential, permissions, isBuiltinProject, {
      onEdit: setCredentialToEdit,
      onDelete: openDeleteDialog,
    })
  }

  // Query state handling (loading/error)
  const queryState = useQueryState(query, {
    title: 'Error loading credentials',
    onRetry: () => detachPromise(query.refetch()),
  })
  if (queryState) {
    return (
      <SynPage>
        <SynPageTitle segments={['Credentials']} />
        <SynPageHeader title="Credentials" docLink={credentialsDocLink} projectSelector={ProjectSelector} />
        <SynPageBody>
          <SynPanel isFullHeight>{queryState}</SynPanel>
        </SynPageBody>
      </SynPage>
    )
  }

  return (
    <SynPage>
      <SynPageTitle segments={['Credentials']} />
      <SynPageHeader
        title="Credentials"
        docLink={credentialsDocLink}
        projectSelector={ProjectSelector}
        toolbar={
          credentials.length > 0 || hasActiveFilters ? (
            <CredentialPageToolbar
              permissions={permissions}
              isBuiltinProject={isBuiltinSelected}
              onCreateClick={() => setCreateModalOpen(true)}
            />
          ) : undefined
        }
      />

      {credentials.length === 0 && !hasActiveFilters ? (
        <SynPageBody>
          <SynPanel isFullHeight>
            <CredentialEmptyState
              onCreateCredential={
                permissions.canCreate && !isBuiltinSelected ? () => setCreateModalOpen(true) : undefined
              }
            />
          </SynPanel>
        </SynPageBody>
      ) : (
        <SynPageBody>
          <SynPanel isFullHeight>
            <SynPanelContentStack>
              <StackItem>
                <FilterBar
                  fieldDefinitions={filterFieldDefinitions}
                  filters={filters}
                  onFilterChange={handleFilterChange}
                  showClearAll={true}
                />
              </StackItem>

              {credentials.length === 0 ? (
                <SynPageBody isCentered>
                  <SynEmptyStateFilter clearAllFilters={handleClearAllFilters} />
                </SynPageBody>
              ) : (
                <SynScrollableTableContainer
                  isExpandable
                  caption="Credentials table"
                  footer={getFooterProps(query.data)}
                >
                  <Thead>
                    <Tr>
                      <Th
                        expand={{
                          areAllExpanded,
                          collapseAllAriaLabel: areAllExpanded ? 'Collapse all' : 'Expand all',
                          onToggle: handleToggleAllRows,
                        }}
                        aria-label="Row expansion"
                      />
                      <Th sort={getSortParams(0)}>Name</Th>
                      <Th>Type</Th>
                      <Th>Workflows</Th>
                      <Th>Integrations</Th>
                      <Th sort={getSortParams(3)}>Created</Th>
                      <Th sort={getSortParams(4)}>Last modified</Th>
                      <Th>State</Th>
                      <Th screenReaderText="Actions" />
                    </Tr>
                  </Thead>
                  {isAllProjects && groupedCredentials ? (
                    <GroupedCredentialsTableBody
                      groupedCredentials={groupedCredentials}
                      collapsedProjects={collapsedProjects}
                      onToggleProject={toggleProjectCollapsed}
                      typeMap={typeMap}
                      expandedRows={expandedRows}
                      onToggleRow={handleToggleRow}
                      getRowActions={getRowActions}
                      onToggleEnabled={handleToggleEnabled}
                      getToggleDisabledTooltip={getToggleDisabledTooltip}
                    />
                  ) : (
                    <FlatCredentialsTableBody
                      credentials={credentials}
                      typeMap={typeMap}
                      expandedRows={expandedRows}
                      onToggleRow={handleToggleRow}
                      getRowActions={getRowActions}
                      onToggleEnabled={handleToggleEnabled}
                      getToggleDisabledTooltip={getToggleDisabledTooltip}
                    />
                  )}
                </SynScrollableTableContainer>
              )}
            </SynPanelContentStack>
          </SynPanel>
        </SynPageBody>
      )}

      <DisableCredentialDialog
        credential={credentialToDisable}
        affectedWorkflows={affectedWorkflows}
        workflowsFetchError={workflowsFetchError}
        isLoadingWorkflows={disableIsLoadingWorkflows}
        affectedIntegrations={disableAffectedIntegrations}
        integrationsFetchError={disableIntegrationsFetchError}
        isLoadingIntegrations={disableIsLoadingIntegrations}
        isLoading={isPatchPending}
        onConfirm={handleConfirmDisable}
        onClose={closeDisableDialog}
      />

      <DeleteCredentialDialog
        credential={credentialToDelete}
        affectedWorkflows={deleteAffectedWorkflows}
        workflowsFetchError={deleteWorkflowsFetchError}
        isLoadingWorkflows={deleteIsLoadingWorkflows}
        affectedIntegrations={deleteAffectedIntegrations}
        integrationsFetchError={deleteIntegrationsFetchError}
        isLoadingIntegrations={deleteIsLoadingIntegrations}
        isLoading={isDeletePending}
        onConfirm={() => handleConfirmDelete(credentialToDelete)}
        onClose={closeDeleteDialog}
      />

      <CredentialFormModal
        isOpen={createModalOpen || !!credentialToEdit}
        onClose={() => {
          setCreateModalOpen(false)
          setCredentialToEdit(null)
        }}
        credentialToEdit={credentialToEdit}
        onSuccess={() => detachPromise(query.refetch())}
        defaultProjectId={selectedProject?.id}
      />
    </SynPage>
  )
}
