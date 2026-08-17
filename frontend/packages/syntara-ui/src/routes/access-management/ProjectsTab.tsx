import { Button, Content, List, ListItem, Stack, StackItem, Truncate } from '@patternfly/react-core'
import { RhUiAddIcon, RhUiEditFillIcon, RhUiTrashIcon } from '@patternfly/react-icons'
import { ActionsColumn, Tbody, Td, Th, Thead, Tr } from '@patternfly/react-table'
import type { IAction, ThProps } from '@patternfly/react-table'
import { useNavigate } from '@tanstack/react-router'
import { useCallback, useMemo } from 'react'

import { AppRoute } from '../../app/AppRoute'
import { NxConfirmationDialog } from '../../components/dialogs/NxConfirmationDialog'
import { DisabledWithTooltip } from '../../components/DisabledWithTooltip'
import { IconLabel } from '../../components/IconLabel'
import { NxListPanelTable, NxListPanelToolbar, NxListPanelView } from '../../components/panels/list/NxListPanel'
import { NxEmptyStateNoData } from '../../components/states/NxEmptyStateNoData'
import { DateCell } from '../../components/table/DateCell'
import { useCursorPagination, useCursorReset } from '../../hooks/useCursorPagination'
import { useDialogState } from '../../hooks/useDialogState'
import { useTableSort } from '../../hooks/useTableSort'
import { useAlerts } from '../../providers/alerts'
import type { FilterFieldDefinition } from '../../types/filters'
import { FilterOperatorEnum, FilterTypeEnum } from '../../types/filters'
import { getErrorMessage } from '../../utils/apiErrors'
import { detachPromise } from '../../utils/detachPromise'
import { accessClient } from '../access/accessClient'
import type { ProjectRead } from '../access/types'

import { ProjectFormModal } from './ProjectFormModal'
import { useProjectPermissions } from './useProjectPermissions'

const filterFieldDefinitions: FilterFieldDefinition[] = [
  {
    key: 'name',
    label: 'Name',
    type: FilterTypeEnum.TEXT,
    operators: [FilterOperatorEnum.CONTAINS],
    defaultOperator: FilterOperatorEnum.CONTAINS,
    placeholder: 'Filter by name',
  },
  {
    key: 'description',
    label: 'Description',
    type: FilterTypeEnum.TEXT,
    operators: [FilterOperatorEnum.CONTAINS],
    defaultOperator: FilterOperatorEnum.CONTAINS,
    placeholder: 'Filter by description',
  },
]

function getRowActions(
  project: ProjectRead,
  onEdit: (p: ProjectRead) => void,
  onDelete: (p: ProjectRead) => void,
  permissions: ReturnType<typeof useProjectPermissions>
): IAction[] {
  return [
    {
      title: <IconLabel icon={<RhUiEditFillIcon />}>Edit</IconLabel>,
      isAriaDisabled: !permissions.canUpdate,
      tooltipProps: permissions.canUpdate ? undefined : { content: permissions.tooltips.update },
      onClick: permissions.canUpdate ? () => onEdit(project) : undefined,
    },
    { isSeparator: true },
    {
      title: <IconLabel icon={<RhUiTrashIcon />}>Delete</IconLabel>,
      isAriaDisabled: !permissions.canDelete,
      tooltipProps: permissions.canDelete ? undefined : { content: permissions.tooltips.delete },
      onClick: permissions.canDelete ? () => onDelete(project) : undefined,
    },
  ]
}

function ProjectRow({
  project,
  onEdit,
  onDelete,
}: Readonly<{
  project: ProjectRead
  onEdit: (p: ProjectRead) => void
  onDelete: (p: ProjectRead) => void
}>) {
  const navigate = useNavigate()
  const permissions = useProjectPermissions({
    resourceProject: project.name || project.id || undefined,
  })

  return (
    <Tr>
      <Td dataLabel="Name">
        <Button
          variant="link"
          isInline
          onClick={() =>
            detachPromise(
              navigate({ to: AppRoute.AccessManagement.ProjectDetail.replace(':projectId', project.id ?? '') })
            )
          }
        >
          <Truncate content={project.name ?? ''} />
        </Button>
      </Td>
      <Td dataLabel="Description">
        <Truncate content={project.description ?? ''} />
      </Td>
      <Td dataLabel="Created">
        <DateCell dateString={project.created_at} />
      </Td>
      <Td dataLabel="Updated">
        <DateCell dateString={project.updated_at} />
      </Td>
      <Td isActionCell>
        <ActionsColumn items={getRowActions(project, onEdit, onDelete, permissions)} />
      </Td>
    </Tr>
  )
}

function ProjectsTable({
  projects,
  getSortParams,
  onEdit,
  onDelete,
}: Readonly<{
  projects: ProjectRead[]
  getSortParams: (columnIndex: number) => ThProps['sort']
  onEdit: (p: ProjectRead) => void
  onDelete: (p: ProjectRead) => void
}>) {
  return (
    <>
      <Thead>
        <Tr>
          <Th sort={getSortParams(0)}>Name</Th>
          <Th>Description</Th>
          <Th sort={getSortParams(2)}>Created</Th>
          <Th sort={getSortParams(3)}>Updated</Th>
          <Th screenReaderText="Actions" />
        </Tr>
      </Thead>
      <Tbody>
        {projects.map((project) => (
          <ProjectRow key={project.id} project={project} onEdit={onEdit} onDelete={onDelete} />
        ))}
      </Tbody>
    </>
  )
}

function DeleteProjectDialog({
  project,
  isOpen,
  onClose,
  onDelete,
}: Readonly<{
  project: ProjectRead | null
  isOpen: boolean
  onClose: () => void
  onDelete: () => void
}>) {
  return (
    <NxConfirmationDialog
      isOpen={isOpen}
      onClose={onClose}
      onConfirm={onDelete}
      title="Delete project?"
      confirmLabel="Delete"
      confirmVariant="danger"
      titleIconVariant="warning"
      destructiveAcknowledgement={{
        checkboxId: 'delete-project-ack',
        label: 'I understand this project, its workflows, and role assignments will be permanently deleted or removed.',
      }}
    >
      <Stack hasGutter>
        <StackItem>
          The project <strong>{project?.name}</strong> will be deleted. This cannot be undone.
        </StackItem>
        <StackItem>
          <List>
            <ListItem>All workflows in this project will be permanently deleted.</ListItem>
            <ListItem>All project role assignments will be removed.</ListItem>
          </List>
        </StackItem>
      </Stack>
    </NxConfirmationDialog>
  )
}

const SORT_FIELDS: Record<number, string> = {
  0: 'name',
  2: 'created_at',
  3: 'updated_at',
}

export function ProjectsTab() {
  const permissions = useProjectPermissions()
  const deleteDialog = useDialogState<ProjectRead>()
  const formDialog = useDialogState<ProjectRead | null>()
  const { showAlert } = useAlerts()

  const {
    cursor,
    resetPagination,
    filters,
    hasActiveFilters,
    queryParams,
    handleFilterChange,
    handleClearAllFilters,
    getFooterProps,
  } = useCursorPagination()

  const { activeSortIndex, sortDirection, getSortParams } = useTableSort({
    initialDirection: 'asc',
    onSortChange: resetPagination,
  })

  const finalQueryParams = useMemo(() => {
    const field = SORT_FIELDS[activeSortIndex] ?? 'name'
    const sort = sortDirection === 'desc' ? `-${field}` : field
    return { ...queryParams, sort }
  }, [activeSortIndex, sortDirection, queryParams])

  const query = accessClient.useQuery('get', '/projects', { params: { query: finalQueryParams } })
  const data = query.data
  const projects = data?.resources ?? []
  const refetch = useCallback(() => detachPromise(query.refetch()), [query])

  useCursorReset(projects.length, hasActiveFilters, cursor, query.isFetching, resetPagination)

  const { mutate: deleteProject } = accessClient.useMutation('delete', '/projects/{project_id}')

  const handleDelete = () => {
    const project = deleteDialog.item
    if (!project) return
    deleteProject(
      { params: { path: { project_id: project.id ?? '' } } },
      {
        onSuccess: () => {
          showAlert({
            title: 'Project deleted',
            description: `Project "${project.name}" has been deleted successfully.`,
            variant: 'success',
            autoDismiss: true,
          })
          refetch()
        },
        onError: (deleteError: unknown) => {
          showAlert({
            title: 'Delete failed',
            description: `Failed to delete project "${project.name}": ${getErrorMessage(deleteError)}`,
            variant: 'error',
            autoDismiss: true,
          })
        },
        onSettled: () => {
          deleteDialog.close()
        },
      }
    )
  }

  return (
    <>
      <NxListPanelView
        tabKey="projects"
        tabLabel="Projects"
        isPending={query.isPending}
        isFetching={query.isFetching}
        error={query.error}
        onRetry={refetch}
        isEmpty={projects.length === 0}
        hasActiveFilters={hasActiveFilters}
        onClearAllFilters={handleClearAllFilters}
        noDataState={
          <NxEmptyStateNoData
            title="No projects yet"
            description="Create a project to organize workflows and manage access."
            buttonText="Create project"
            addData={permissions.canCreate ? () => formDialog.open(null) : undefined}
          />
        }
        toolbar={
          projects.length > 0 || hasActiveFilters ? (
            <NxListPanelToolbar
              filters={filters}
              filterDefinitions={filterFieldDefinitions}
              onFilterChange={handleFilterChange}
              clearAllFilters={handleClearAllFilters}
              actions={
                <DisabledWithTooltip isDisabled={!permissions.canCreate} content={permissions.tooltips.create}>
                  <Button
                    variant="primary"
                    icon={<RhUiAddIcon />}
                    isAriaDisabled={!permissions.canCreate}
                    onClick={permissions.canCreate ? () => formDialog.open(null) : undefined}
                  >
                    Create project
                  </Button>
                </DisabledWithTooltip>
              }
            />
          ) : undefined
        }
        body={
          <>
            <Content>
              Projects organize workflows and their resources, such as credentials, into separate workspaces. Each
              workflow and credential belongs to exactly one project. Use projects to keep related automation work
              together and to control access through role assignments.
            </Content>
            <NxListPanelTable caption="Projects" footer={getFooterProps(data)}>
              <ProjectsTable
                projects={projects}
                getSortParams={getSortParams}
                onEdit={(p) => formDialog.open(p)}
                onDelete={(p) => deleteDialog.open(p)}
              />
            </NxListPanelTable>
          </>
        }
      />

      <ProjectFormModal
        project={formDialog.item}
        isOpen={formDialog.isOpen}
        onClose={formDialog.close}
        onSuccess={refetch}
      />

      <DeleteProjectDialog
        project={deleteDialog.item}
        isOpen={deleteDialog.isOpen}
        onClose={deleteDialog.close}
        onDelete={handleDelete}
      />
    </>
  )
}
