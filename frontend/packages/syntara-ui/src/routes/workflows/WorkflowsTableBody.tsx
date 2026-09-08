import { Flex, FlexItem, Truncate } from '@patternfly/react-core'
import { RhUiCaretDownIcon, RhUiCaretRightIcon } from '@patternfly/react-icons'
import { Tbody, Td, Tr } from '@patternfly/react-table'
import type { WorkflowAPI } from '@syntara/contracts'

import groupedTableStyles from '../../components/groupedTable.module.css'
import type { KebabAction } from '../../components/SynKebabMenu'
import { SynKebabMenu } from '../../components/SynKebabMenu'
import { DateCell } from '../../components/table/DateCell'
import { LinkCell } from '../../components/table/LinkCell'
import { WorkflowPublishStatusBadge } from '../../components/WorkflowPublishStatusBadge'
import { getDateField } from '../../utils/getDateField'
import type { ProjectRead } from '../access/types'
import { useProjectPermissions } from '../access-management/useProjectPermissions'

import { buildProjectRowActions, type ProjectRowActionCallbacks } from './projectRowActions'

type Workflow = WorkflowAPI.components['schemas']['WorkflowRead']

export type RowAction = KebabAction

type WorkflowRowProps = {
  workflow: Workflow
  getRowActions: (workflow: Workflow) => RowAction[]
}

function WorkflowRow({ workflow, getRowActions }: Readonly<WorkflowRowProps>) {
  const actions = getRowActions(workflow)

  return (
    <Tr key={workflow.id}>
      <Td dataLabel="Name">
        <LinkCell href={`/workflow-builder/${workflow.id}`}>
          <Truncate content={workflow.name ?? ''} />
        </LinkCell>
      </Td>
      <Td dataLabel="Created at">
        <DateCell dateString={getDateField(workflow, 'createdAt')} />
      </Td>
      <Td dataLabel="Updated at">
        <DateCell dateString={getDateField(workflow, 'updatedAt')} />
      </Td>
      <Td dataLabel="Status">
        <WorkflowPublishStatusBadge
          publishedVersionId={workflow.published_version_id}
          hasUnpublishedChanges={
            workflow.published_version_number != null && workflow.published_version_number !== workflow.current_version
          }
        />
      </Td>
      <Td isActionCell>
        {actions.length > 0 && <SynKebabMenu actions={actions} aria-label={`Actions for ${workflow.name}`} />}
      </Td>
    </Tr>
  )
}

type ProjectGroup = {
  project: ProjectRead | null
  workflows: Workflow[]
}

type ProjectGroupSectionProps = {
  projectId: string
  project: ProjectRead | null
  workflows: Workflow[]
  isCollapsed: boolean
  onToggleProject: (projectId: string) => void
  getRowActions: (workflow: Workflow) => RowAction[]
  projectActionCallbacks?: ProjectRowActionCallbacks
}

function ProjectGroupSection({
  projectId,
  project,
  workflows,
  isCollapsed,
  onToggleProject,
  getRowActions,
  projectActionCallbacks,
}: Readonly<ProjectGroupSectionProps>) {
  const permissions = useProjectPermissions({
    // UUID — matches builder / workflows list can_i cache keys (API resolves to name).
    resourceProject: project?.id,
  })
  const projectActions = projectActionCallbacks
    ? buildProjectRowActions(project, permissions, projectActionCallbacks)
    : []
  const hasProjectActions = projectActions.length > 0

  return (
    <Tbody>
      <Tr className={groupedTableStyles.groupHeader}>
        <Td colSpan={hasProjectActions ? 4 : 5} onClick={() => onToggleProject(projectId)}>
          <Flex alignItems={{ default: 'alignItemsCenter' }} gap={{ default: 'gapSm' }}>
            <FlexItem>{isCollapsed ? <RhUiCaretRightIcon /> : <RhUiCaretDownIcon />}</FlexItem>
            <FlexItem>
              <strong>{project?.name ?? (projectId === 'unknown' ? 'No project' : projectId)}</strong>
            </FlexItem>
          </Flex>
        </Td>
        {hasProjectActions && (
          <Td isActionCell onClick={(e) => e.stopPropagation()}>
            <SynKebabMenu actions={projectActions} aria-label={`Actions for ${project?.name ?? 'project'}`} />
          </Td>
        )}
      </Tr>
      {!isCollapsed &&
        workflows.map((workflow) => (
          <WorkflowRow key={workflow.id} workflow={workflow} getRowActions={getRowActions} />
        ))}
    </Tbody>
  )
}

type GroupedWorkflowsTableBodyProps = {
  groupedWorkflows: Map<string, ProjectGroup>
  collapsedProjects: Set<string>
  onToggleProject: (projectId: string) => void
  getRowActions: (workflow: Workflow) => RowAction[]
  projectActionCallbacks?: ProjectRowActionCallbacks
}

export function GroupedWorkflowsTableBody({
  groupedWorkflows,
  collapsedProjects,
  onToggleProject,
  getRowActions,
  projectActionCallbacks,
}: Readonly<GroupedWorkflowsTableBodyProps>) {
  return (
    <>
      {[...groupedWorkflows.entries()].map(([projectId, { project, workflows }]) => (
        <ProjectGroupSection
          key={projectId}
          projectId={projectId}
          project={project}
          workflows={workflows}
          isCollapsed={collapsedProjects.has(projectId)}
          onToggleProject={onToggleProject}
          getRowActions={getRowActions}
          projectActionCallbacks={projectActionCallbacks}
        />
      ))}
    </>
  )
}

type FlatWorkflowsTableBodyProps = {
  workflows: Workflow[]
  getRowActions: (workflow: Workflow) => RowAction[]
}

export function FlatWorkflowsTableBody({ workflows, getRowActions }: Readonly<FlatWorkflowsTableBodyProps>) {
  return (
    <Tbody>
      {workflows.map((workflow) => (
        <WorkflowRow key={workflow.id} workflow={workflow} getRowActions={getRowActions} />
      ))}
    </Tbody>
  )
}
