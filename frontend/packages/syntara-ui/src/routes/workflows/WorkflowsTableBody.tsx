import { Button, Content, Flex, FlexItem, Truncate } from '@patternfly/react-core'
import { RhUiCaretDownIcon, RhUiCaretRightIcon } from '@patternfly/react-icons'
import { Tbody, Td, Tr } from '@patternfly/react-table'
import type { WorkflowAPI } from '@syntara/contracts'
import { useState } from 'react'

import groupedTableStyles from '../../components/groupedTable.module.css'
import { SynLabel } from '../../components/labels/SynLabel'
import type { KebabAction } from '../../components/SynKebabMenu'
import { SynKebabMenu } from '../../components/SynKebabMenu'
import { LinkCell } from '../../components/table/LinkCell'
import { UserTimestamp } from '../../components/table/UserTimestamp'
import { WorkflowPublishStatusBadge } from '../../components/WorkflowPublishStatusBadge'
import type { ProjectRead } from '../access/types'
import { useProjectPermissions } from '../access-management/useProjectPermissions'

import { buildProjectRowActions, type ProjectRowActionCallbacks } from './projectRowActions'
import { useWorkflowPermissions } from './useWorkflowPermissions'
import { useWorkflowUsedByCountsContext } from './useWorkflowUsedBy'
import { buildWorkflowRowActions, type WorkflowRowActionCallbacks } from './workflowRowActions'
import { WorkflowUsedByModal } from './WorkflowUsedByModal'

type Workflow = WorkflowAPI.components['schemas']['WorkflowRead']

export type RowAction = KebabAction

/**
 * "Used by" cell: a plain number for zero / unknown counts, and a clickable gray count that opens
 * the Used-By drill-down modal when one or more published workflows use this workflow. Using a
 * click-opened modal (rather than a hover popover with a semantic list) keeps the parent list
 * reachable for assistive technology and scalable to many parents.
 */
function UsedByCell({ workflowId, count }: { readonly workflowId: string; readonly count: number | undefined }) {
  const [isModalOpen, setIsModalOpen] = useState(false)
  if (count === undefined) return <Content component="small">—</Content>
  if (count === 0) return <Content component="small">0</Content>
  return (
    <>
      <Button
        variant="plain"
        onClick={() => setIsModalOpen(true)}
        aria-label={`Used by ${count} published workflows. View list.`}
      >
        <SynLabel color="grey">{`${count} workflow${count === 1 ? '' : 's'}`}</SynLabel>
      </Button>
      {isModalOpen && <WorkflowUsedByModal isOpen onClose={() => setIsModalOpen(false)} workflowId={workflowId} />}
    </>
  )
}

type WorkflowRowProps = {
  workflow: Workflow
  isBuiltinProject?: boolean
  rowActionCallbacks?: WorkflowRowActionCallbacks
  showRowActions?: boolean
}

function WorkflowRow({
  workflow,
  isBuiltinProject = false,
  rowActionCallbacks,
  showRowActions = true,
}: Readonly<WorkflowRowProps>) {
  const [rowChecksEnabled, setRowChecksEnabled] = useState(false)
  const usedByCounts = useWorkflowUsedByCountsContext()
  const usedByCount = usedByCounts.get(workflow.id)
  const permissions = useWorkflowPermissions({
    resourceProject: workflow.project_id,
    enabled: showRowActions && rowChecksEnabled,
  })
  const actions =
    showRowActions && rowActionCallbacks
      ? buildWorkflowRowActions(workflow, permissions, isBuiltinProject, rowActionCallbacks)
      : []

  return (
    <Tr key={workflow.id}>
      <Td dataLabel="Name">
        <LinkCell href={`/workflow-builder/${workflow.id}`}>
          <Truncate content={workflow.name ?? ''} />
        </LinkCell>
      </Td>
      <Td dataLabel="Created at">
        <UserTimestamp user={workflow.created_by} timestamp={workflow.created_at} inline />
      </Td>
      <Td dataLabel="Updated at">
        <UserTimestamp user={workflow.updated_by} timestamp={workflow.updated_at} inline />
      </Td>
      <Td dataLabel="Used by">
        <UsedByCell workflowId={workflow.id} count={usedByCount} />
      </Td>
      <Td dataLabel="State">
        <WorkflowPublishStatusBadge
          publishedVersionId={workflow.published_version_id}
          hasUnpublishedChanges={
            workflow.published_version_number != null && workflow.published_version_number !== workflow.current_version
          }
        />
      </Td>
      {showRowActions && (
        <Td isActionCell>
          {actions.length > 0 && (
            <SynKebabMenu
              actions={actions}
              aria-label={`Actions for ${workflow.name}`}
              onOpenChange={(isOpen) => {
                if (isOpen) setRowChecksEnabled(true)
              }}
            />
          )}
        </Td>
      )}
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
  isWorkflowProjectBuiltin?: (workflow: Workflow) => boolean
  rowActionCallbacks?: WorkflowRowActionCallbacks
  showRowActions?: boolean
  projectActionCallbacks?: ProjectRowActionCallbacks
}

function ProjectGroupSection({
  projectId,
  project,
  workflows,
  isCollapsed,
  onToggleProject,
  isWorkflowProjectBuiltin,
  rowActionCallbacks,
  showRowActions = true,
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
  const totalColumns = 5 + (showRowActions ? 1 : 0)
  const headerColSpan = hasProjectActions ? totalColumns - 1 : totalColumns

  return (
    <Tbody>
      <Tr className={groupedTableStyles.groupHeader}>
        <Td colSpan={headerColSpan} onClick={() => onToggleProject(projectId)}>
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
          <WorkflowRow
            key={workflow.id}
            workflow={workflow}
            isBuiltinProject={isWorkflowProjectBuiltin?.(workflow) ?? false}
            rowActionCallbacks={rowActionCallbacks}
            showRowActions={showRowActions}
          />
        ))}
    </Tbody>
  )
}

type GroupedWorkflowsTableBodyProps = {
  groupedWorkflows: Map<string, ProjectGroup>
  collapsedProjects: Set<string>
  onToggleProject: (projectId: string) => void
  isWorkflowProjectBuiltin?: (workflow: Workflow) => boolean
  rowActionCallbacks?: WorkflowRowActionCallbacks
  showRowActions?: boolean
  projectActionCallbacks?: ProjectRowActionCallbacks
}

export function GroupedWorkflowsTableBody({
  groupedWorkflows,
  collapsedProjects,
  onToggleProject,
  isWorkflowProjectBuiltin,
  rowActionCallbacks,
  showRowActions = true,
  projectActionCallbacks,
}: GroupedWorkflowsTableBodyProps) {
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
          isWorkflowProjectBuiltin={isWorkflowProjectBuiltin}
          rowActionCallbacks={rowActionCallbacks}
          showRowActions={showRowActions}
          projectActionCallbacks={projectActionCallbacks}
        />
      ))}
    </>
  )
}

type FlatWorkflowsTableBodyProps = {
  workflows: Workflow[]
  isWorkflowProjectBuiltin?: (workflow: Workflow) => boolean
  rowActionCallbacks?: WorkflowRowActionCallbacks
  showRowActions?: boolean
}

export function FlatWorkflowsTableBody({
  workflows,
  isWorkflowProjectBuiltin,
  rowActionCallbacks,
  showRowActions = true,
}: Readonly<FlatWorkflowsTableBodyProps>) {
  return (
    <Tbody>
      {workflows.map((workflow) => (
        <WorkflowRow
          key={workflow.id}
          workflow={workflow}
          isBuiltinProject={isWorkflowProjectBuiltin?.(workflow) ?? false}
          rowActionCallbacks={rowActionCallbacks}
          showRowActions={showRowActions}
        />
      ))}
    </Tbody>
  )
}
