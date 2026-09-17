import { Button, Content, Truncate } from '@patternfly/react-core'
import { RhUiAddIcon, RhUiEditFillIcon, RhUiTrashIcon } from '@patternfly/react-icons'
import { Tbody, Td, Th, Thead, Tr } from '@patternfly/react-table'
import type { ThProps } from '@patternfly/react-table'
import { useNavigate } from '@tanstack/react-router'
import { useCallback, useMemo } from 'react'

import { AppRoute } from '../../app/AppRoute'
import { DisabledWithTooltip } from '../../components/DisabledWithTooltip'
import { IconLabel } from '../../components/IconLabel'
import { SynListPanelTable, SynListPanelToolbar, SynListPanelView } from '../../components/panels/list/SynListPanel'
import { SynEmptyStateNoData } from '../../components/states/SynEmptyStateNoData'
import { SynKebabMenu, type KebabAction } from '../../components/SynKebabMenu'
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
import { ProjectDeleteDialog } from './projects/ProjectDeleteDialog'
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
): KebabAction[] {
  return [
    {
      key: 'edit',
      title: <IconLabel icon={<RhUiEditFillIcon />}>Edit project</IconLabel>,
      isAriaDisabled: !permissions.canUpdate,
      tooltipProps: permissions.canUpdate ? undefined : { content: permissions.tooltips.update },
      onClick: permissions.canUpdate ? () => onEdit(project) : undefined,
    },
    { key: 'sep-delete', isSeparator: true },
    {
      key: 'delete',
      title: <IconLabel icon={<RhUiTrashIcon />}>Delete project</IconLabel>,
      isDanger: true,
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
        <SynKebabMenu
          actions={getRowActions(project, onEdit, onDelete, permissions)}
          aria-label={`Actions for ${project.name}`}
        />
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
      <SynListPanelView
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
          <SynEmptyStateNoData
            title="No projects yet"
            description="Create a project to organize workflows and manage access."
            buttonText="Create project"
            addData={permissions.canCreate ? () => formDialog.open(null) : undefined}
          />
        }
        toolbar={
          projects.length > 0 || hasActiveFilters ? (
            <SynListPanelToolbar
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
            <SynListPanelTable caption="Projects" footer={getFooterProps(data)}>
              <ProjectsTable
                projects={projects}
                getSortParams={getSortParams}
                onEdit={(p) => formDialog.open(p)}
                onDelete={(p) => deleteDialog.open(p)}
              />
            </SynListPanelTable>
          </>
        }
      />

      <ProjectFormModal
        project={formDialog.item}
        isOpen={formDialog.isOpen}
        onClose={formDialog.close}
        onSuccess={refetch}
      />

      <ProjectDeleteDialog
        projectName={deleteDialog.item?.name}
        isOpen={deleteDialog.isOpen}
        onClose={deleteDialog.close}
        onConfirm={handleDelete}
      />
    </>
  )
}
