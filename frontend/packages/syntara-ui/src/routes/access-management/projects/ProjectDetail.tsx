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
  List,
  ListItem,
  Stack,
  StackItem,
  Tab,
  TabTitleText,
} from '@patternfly/react-core'
import { RhUiEditIcon, RhUiTrashIcon } from '@patternfly/react-icons'
import { useNavigate, useParams } from '@tanstack/react-router'
import { useMemo, useState } from 'react'

import { AppRoute } from '../../../app/AppRoute'
import { breadcrumbsProjectDetail, breadcrumbsProjectDetailEarlyShell } from '../../../app/breadcrumbBuilders'
import { SynConfirmationDialog } from '../../../components/dialogs/SynConfirmationDialog'
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
import { useUrlTab } from '../../../hooks/useUrlTab'
import { detachPromise } from '../../../utils/detachPromise'
import { useDocLink } from '../../../utils/docs/useDocLink'
import { accessClient } from '../../access/accessClient'
import type { ProjectRead } from '../../access/types'
import { DetailPageShell } from '../DetailPageShell'
import { ProjectFormModal } from '../ProjectFormModal'
import { useProjectPermissions } from '../useProjectPermissions'

import { ProjectNotFoundState } from './ProjectNotFoundState'
import { ProjectRoleAssignmentsTab } from './ProjectRoleAssignmentsTab'
import { useProjectDetailPermissions } from './useProjectDetailPermissions'

const noop = () => {}

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

type ProjectTab = 'details' | 'role-assignments'
const ALL_PROJECT_TABS: ProjectTab[] = ['details', 'role-assignments']

export function ProjectDetail() {
  const navigate = useNavigate()
  const projectsDocLink = useDocLink('projects')
  const { projectId }: { projectId: string } = useParams({ strict: false })
  const basePath = AppRoute.AccessManagement.ProjectDetail.replace(':projectId', projectId ?? '')
  const [activeTab] = useUrlTab<ProjectTab>(basePath)
  const [editModalOpen, setEditModalOpen] = useState(false)
  const deleteDialog = useDialogState<ProjectRead>()
  const projectPermissions = useProjectPermissions({ resourceProject: projectId })
  const { canReadAssignments, isLoading: permissionsLoading } = useProjectDetailPermissions(projectId ?? '')
  const { mutate: deleteProject } = accessClient.useMutation('delete', '/projects/{project_id}')

  const validTabs = useMemo(() => {
    if (permissionsLoading || canReadAssignments) return ALL_PROJECT_TABS
    return ALL_PROJECT_TABS.filter((tab) => tab !== 'role-assignments')
  }, [canReadAssignments, permissionsLoading])

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

  if (!projectData) return null

  const projectCrumbs = breadcrumbsProjectDetail(projectData.name, basePath, activeTab)

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
          <SynListPanelTabs basePath={basePath} defaultTab="details" validTabs={validTabs} aria-label="Project details">
            <Tab eventKey="details" title={<TabTitleText>Details</TabTitleText>} />
            {validTabs.includes('role-assignments') && (
              <Tab eventKey="role-assignments" title={<TabTitleText>Assignments</TabTitleText>} />
            )}
          </SynListPanelTabs>

          {activeTab === 'details' && (
            <SynListPanelView
              tabKey="details"
              tabLabel="Details"
              isPending={false}
              error={null}
              isEmpty={false}
              hasActiveFilters={false}
              onRetry={noop}
              onClearAllFilters={noop}
              body={<ProjectDetailsTab project={projectData} />}
            />
          )}
          {activeTab === 'role-assignments' && validTabs.includes('role-assignments') && (
            <ProjectRoleAssignmentsTab projectId={projectId ?? ''} />
          )}
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

      <SynConfirmationDialog
        isOpen={deleteDialog.isOpen}
        onClose={deleteDialog.close}
        onConfirm={() => handleDelete(deleteDialog.item)}
        title="Delete project?"
        confirmLabel="Delete"
        confirmVariant="danger"
        titleIconVariant="warning"
        destructiveAcknowledgement={{
          checkboxId: 'delete-project-detail-ack',
          label:
            'I understand this project, its workflows, and role assignments will be permanently deleted or removed.',
        }}
      >
        <Stack hasGutter>
          <StackItem>
            The project <strong>{deleteDialog.item?.name}</strong> will be deleted. This cannot be undone.
          </StackItem>
          <StackItem>
            <List>
              <ListItem>All workflows in this project will be permanently deleted.</ListItem>
              <ListItem>All project role assignments will be removed.</ListItem>
              <ListItem>
                Uploaded files are kept after the project is deleted. There is no in-product list or delete flow for
                them yet.
              </ListItem>
            </List>
          </StackItem>
        </Stack>
      </SynConfirmationDialog>
    </SynPage>
  )
}
