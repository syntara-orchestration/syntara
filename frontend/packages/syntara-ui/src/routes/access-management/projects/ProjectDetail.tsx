import {
  Button,
  DescriptionList,
  DescriptionListDescription,
  DescriptionListGroup,
  DescriptionListTerm,
  Flex,
  FlexItem,
  Label,
  LabelGroup,
  Tab,
  TabTitleText,
} from '@patternfly/react-core'
import { RhUiEditIcon, RhUiTrashIcon } from '@patternfly/react-icons'
import { Outlet, useNavigate, useParams, useRouterState } from '@tanstack/react-router'
import { createContext, use, useMemo, useState } from 'react'

import { AppRoute } from '../../../app/AppRoute'
import { breadcrumbsProjectDetail, breadcrumbsProjectDetailEarlyShell } from '../../../app/breadcrumbBuilders'
import { DisabledWithTooltip } from '../../../components/DisabledWithTooltip'
import { IconLabel } from '../../../components/IconLabel'
import { SynLabel } from '../../../components/labels/SynLabel'
import { SynPage, SynPageBody } from '../../../components/layout/SynPage'
import { SynPageHeader } from '../../../components/layout/SynPageHeader'
import { SynListPanel, SynListPanelTabs, SynListPanelView } from '../../../components/panels/list/SynListPanel'
import { useQueryState } from '../../../components/states/useQueryState'
import { SynKebabMenu } from '../../../components/SynKebabMenu'
import { SynPageTitle } from '../../../components/SynPageTitle'
import { DateCell } from '../../../components/table/DateCell'
import { useDeleteAction } from '../../../hooks/useDeleteAction'
import { useDialogState } from '../../../hooks/useDialogState'
import { detachPromise } from '../../../utils/detachPromise'
import { useDocLink } from '../../../utils/docs/useDocLink'
import { accessClient } from '../../access/accessClient'
import type { ProjectRead } from '../../access/types'
import { DetailPageShell } from '../DetailPageShell'
import { ProjectFormModal } from '../ProjectFormModal'
import { useProjectPermissions } from '../useProjectPermissions'

import { ProjectDeleteDialog } from './ProjectDeleteDialog'
import { canShowTabContent, computeProjectTabState, type ProjectTab } from './projectDetailTabs'
import { ProjectNotFoundState } from './ProjectNotFoundState'
import { ProjectRoleAssignmentsTab } from './ProjectRoleAssignmentsTab'
import { ProjectWorkflowsTab } from './ProjectWorkflowsTab'
import { useProjectDetailPermissions } from './useProjectDetailPermissions'

const noop = () => {}

type ProjectDetailRouteContextValue = {
  project: ProjectRead
  projectId: string
  activeTab: ProjectTab
  visibleTabs: ProjectTab[]
  permissionsLoading: boolean
}

const ProjectDetailRouteContext = createContext<ProjectDetailRouteContextValue | null>(null)

function useProjectDetailRouteContext() {
  const context = use(ProjectDetailRouteContext)
  if (!context) throw new Error('Project detail tab routes must be rendered inside ProjectDetail')
  return context
}

export function ProjectDetailDetailsTabRoute() {
  const { project } = useProjectDetailRouteContext()

  return (
    <SynListPanelView
      tabKey="details"
      tabLabel="Details"
      isPending={false}
      error={null}
      isEmpty={false}
      hasActiveFilters={false}
      onRetry={noop}
      onClearAllFilters={noop}
      body={<ProjectDetailsTab project={project} />}
    />
  )
}

export function ProjectDetailWorkflowsTabRoute() {
  const { project, projectId, activeTab, visibleTabs, permissionsLoading } = useProjectDetailRouteContext()
  if (!canShowTabContent('workflows', visibleTabs, permissionsLoading, activeTab)) return null

  return <ProjectWorkflowsTab projectId={projectId} isBuiltin={project.is_builtin} />
}

export function ProjectDetailAssignmentsTabRoute() {
  const { projectId, activeTab, visibleTabs, permissionsLoading } = useProjectDetailRouteContext()
  if (!canShowTabContent('role-assignments', visibleTabs, permissionsLoading, activeTab)) return null

  return <ProjectRoleAssignmentsTab projectId={projectId} />
}

export function ProjectDetailUnknownTabRoute() {
  return null
}

function ProjectDetailToolbar({
  permissions,
  onEdit,
  onDelete,
}: Readonly<{
  permissions: ReturnType<typeof useProjectPermissions>
  onEdit: () => void
  onDelete: () => void
}>) {
  return (
    <>
      <DisabledWithTooltip isDisabled={!permissions.canUpdate} content={permissions.tooltips.update}>
        <Button
          variant="primary"
          icon={<RhUiEditIcon />}
          isAriaDisabled={!permissions.canUpdate}
          onClick={permissions.canUpdate ? onEdit : undefined}
        >
          Edit project
        </Button>
      </DisabledWithTooltip>
      <SynKebabMenu
        actions={[
          {
            key: 'delete',
            title: <IconLabel icon={<RhUiTrashIcon />}>Delete project</IconLabel>,
            isDanger: true,
            onClick: permissions.canDelete ? onDelete : undefined,
            isAriaDisabled: !permissions.canDelete,
            tooltipProps: permissions.canDelete ? undefined : { content: permissions.tooltips.delete },
          },
        ]}
        aria-label="Project actions"
      />
    </>
  )
}

function ProjectDetailsTab({ project }: Readonly<{ project: ProjectRead }>) {
  const labelEntries = Object.entries(project.labels ?? {})

  return (
    <DescriptionList isHorizontal isAutoColumnWidths>
      <DescriptionListGroup>
        <DescriptionListTerm>Name</DescriptionListTerm>
        <DescriptionListDescription>
          <Flex alignItems={{ default: 'alignItemsCenter' }} gap={{ default: 'gapSm' }}>
            <FlexItem>{project.name}</FlexItem>
            {project.is_default && <SynLabel color="grey">Default</SynLabel>}
          </Flex>
        </DescriptionListDescription>
      </DescriptionListGroup>
      <DescriptionListGroup>
        <DescriptionListTerm>Description</DescriptionListTerm>
        <DescriptionListDescription>{project.description ?? '-'}</DescriptionListDescription>
      </DescriptionListGroup>
      <DescriptionListGroup>
        <DescriptionListTerm>Labels</DescriptionListTerm>
        <DescriptionListDescription>
          {labelEntries.length > 0 ? (
            <LabelGroup>
              {labelEntries.map(([key, value]) => (
                <Label key={key} isCompact>
                  {key}: {String(value)}
                </Label>
              ))}
            </LabelGroup>
          ) : (
            '-'
          )}
        </DescriptionListDescription>
      </DescriptionListGroup>
      <DescriptionListGroup>
        <DescriptionListTerm>Created</DescriptionListTerm>
        <DescriptionListDescription>
          <DateCell dateString={project.created_at} />
        </DescriptionListDescription>
      </DescriptionListGroup>
      <DescriptionListGroup>
        <DescriptionListTerm>Updated</DescriptionListTerm>
        <DescriptionListDescription>
          <DateCell dateString={project.updated_at} />
        </DescriptionListDescription>
      </DescriptionListGroup>
    </DescriptionList>
  )
}

export function ProjectDetail() {
  const navigate = useNavigate()
  const projectsDocLink = useDocLink('projects')
  const { projectId }: { projectId: string } = useParams({ strict: false })
  const basePath = AppRoute.AccessManagement.ProjectDetail.replace(':projectId', projectId ?? '')
  const pathname = useRouterState({ select: (state) => state.location.pathname })
  const { activeTab, activeTabSlug } = useMemo(() => {
    const routePath = pathname.startsWith(basePath) ? pathname.slice(basePath.length) : ''
    const activeTabSlug = routePath.split('/').find(Boolean) ?? 'details'
    const activeTab: ProjectTab =
      activeTabSlug === 'workflows' || activeTabSlug === 'role-assignments' ? activeTabSlug : 'details'
    return { activeTab, activeTabSlug }
  }, [pathname, basePath])
  const [editModalOpen, setEditModalOpen] = useState(false)
  const deleteDialog = useDialogState<ProjectRead>()
  const projectPermissions = useProjectPermissions({ resourceProject: projectId })
  const {
    canReadWorkflows,
    canReadAssignments,
    isLoading: permissionsLoading,
  } = useProjectDetailPermissions(projectId ?? '')
  const { mutate: deleteProject } = accessClient.useMutation('delete', '/projects/{project_id}')

  const { visibleTabs, urlValidTabs } = useMemo(
    () => computeProjectTabState(canReadWorkflows, canReadAssignments, permissionsLoading, activeTab),
    [canReadWorkflows, canReadAssignments, permissionsLoading, activeTab]
  )

  const projectQuery = accessClient.useQuery(
    'get',
    '/projects/{project_id}',
    { params: { path: { project_id: projectId ?? '' } } },
    { enabled: !!projectId, retry: false }
  )

  const navigateBack = () => detachPromise(navigate({ to: AppRoute.AccessManagement.Projects }))

  const handleDelete = useDeleteAction({
    deleteFn: deleteProject,
    buildParams: (project: ProjectRead) => ({ params: { path: { project_id: project.id ?? '' } } }),
    entityLabel: 'project',
    getItemName: (project: ProjectRead) => project.name,
    onSuccess: navigateBack,
    onSettled: deleteDialog.close,
  })

  const projectData = projectQuery.data
  const projectDetailRouteContextValue = useMemo<ProjectDetailRouteContextValue | null>(() => {
    if (!projectData) return null
    return {
      project: projectData,
      projectId: projectId ?? '',
      activeTab,
      visibleTabs,
      permissionsLoading,
    }
  }, [projectData, projectId, activeTab, visibleTabs, permissionsLoading])
  const refetchProject = projectQuery.refetch
  const queryState = useQueryState(projectQuery, {
    title: 'Error loading project',
    onRetry: () => {
      refetchProject().catch(() => {})
    },
  })

  if (projectQuery.error) {
    return (
      <DetailPageShell title="Project Details" breadcrumbs={breadcrumbsProjectDetailEarlyShell()}>
        <ProjectNotFoundState
          onBack={navigateBack}
          onRetry={() => {
            refetchProject().catch(() => {})
          }}
        />
      </DetailPageShell>
    )
  }

  if (queryState) {
    return (
      <DetailPageShell title="Project Details" breadcrumbs={breadcrumbsProjectDetailEarlyShell()}>
        {queryState}
      </DetailPageShell>
    )
  }

  if (!projectData || !projectDetailRouteContextValue) return null

  const projectCrumbs = breadcrumbsProjectDetail(projectData.name, basePath, activeTabSlug)

  return (
    <SynPage>
      <SynPageTitle segments={[projectData.name, 'Projects']} />
      <SynPageHeader
        title={projectData.name}
        docLink={projectsDocLink}
        breadcrumbs={projectCrumbs}
        toolbar={
          <ProjectDetailToolbar
            permissions={projectPermissions}
            onEdit={() => setEditModalOpen(true)}
            onDelete={() => deleteDialog.open(projectData)}
          />
        }
      />
      <SynPageBody>
        <SynListPanel>
          <SynListPanelTabs
            basePath={basePath}
            defaultTab="details"
            validTabs={urlValidTabs}
            aria-label="Project details"
          >
            <Tab eventKey="details" title={<TabTitleText>Details</TabTitleText>} />
            {visibleTabs.includes('workflows') && (
              <Tab eventKey="workflows" title={<TabTitleText>Workflows</TabTitleText>} />
            )}
            {visibleTabs.includes('role-assignments') && (
              <Tab eventKey="role-assignments" title={<TabTitleText>Assignments</TabTitleText>} />
            )}
          </SynListPanelTabs>
          <ProjectDetailRouteContext.Provider value={projectDetailRouteContextValue}>
            <Outlet />
          </ProjectDetailRouteContext.Provider>
        </SynListPanel>
      </SynPageBody>

      <ProjectFormModal
        project={projectData}
        isOpen={editModalOpen}
        onClose={() => setEditModalOpen(false)}
        onSuccess={() => {
          detachPromise(projectQuery.refetch())
        }}
      />

      <ProjectDeleteDialog
        projectName={deleteDialog.item?.name}
        isOpen={deleteDialog.isOpen}
        onClose={deleteDialog.close}
        onConfirm={() => handleDelete(deleteDialog.item)}
      />
    </SynPage>
  )
}
