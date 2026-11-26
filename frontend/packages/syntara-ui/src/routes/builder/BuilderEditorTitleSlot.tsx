import { Flex, FlexItem, TextInput, Tooltip } from '@patternfly/react-core'
import type { Dispatch, ReactNode } from 'react'

import { WorkflowPublishStatusBadge } from '../../components/WorkflowPublishStatusBadge'

import type { BuilderAction } from './builderReducer'
import styles from './BuilderWorkflowPageHeader.module.css'
import { EditWorkflowDetailsPopover } from './EditWorkflowDetailsPopover'
import type { BuilderPermissions } from './useBuilderPermissions'
import { WorkflowReferencedByBadge } from './WorkflowReferencedByBadge'

type BuilderEditorTitleSlotProps = Readonly<{
  workflowName: string
  workflowDescription: string
  workflowId?: string
  isNew: boolean
  publishedVersionId: string | null
  currentVersionId?: string | null
  isBuiltin: boolean
  builderPermissions: BuilderPermissions
  ProjectSelector: ReactNode
  dispatch: Dispatch<BuilderAction>
  markDirty: () => void
}>

export function BuilderEditorTitleSlot({
  workflowName,
  workflowDescription,
  workflowId,
  isNew,
  publishedVersionId,
  currentVersionId,
  isBuiltin,
  builderPermissions,
  ProjectSelector,
  dispatch,
  markDirty,
}: BuilderEditorTitleSlotProps) {
  return (
    <Flex
      className={styles.titleSlot}
      data-testid="builder-title-slot"
      gap={{ default: 'gapMd' }}
      alignItems={{ default: 'alignItemsCenter' }}
      flexWrap={{ default: 'wrap' }}
    >
      <FlexItem className={styles.workflowName} data-testid="builder-workflow-name">
        <Tooltip
          content={builderPermissions.tooltips.edit}
          trigger={builderPermissions.canEdit ? 'manual' : 'mouseenter focus'}
        >
          <TextInput
            id="workflow-name-input"
            type="text"
            aria-label="Workflow name"
            value={workflowName}
            isDisabled={!builderPermissions.canEdit}
            onChange={(_event, value) => {
              dispatch({ type: 'SET_WORKFLOW_NAME', payload: value })
              markDirty()
            }}
            placeholder="Workflow name"
          />
        </Tooltip>
      </FlexItem>
      {builderPermissions.canEdit && (
        <FlexItem flex={{ default: 'flexNone' }}>
          <EditWorkflowDetailsPopover
            name={workflowName}
            description={workflowDescription}
            onApply={(name, description) => {
              const nameChanged = name !== workflowName
              const descriptionChanged = description !== workflowDescription
              if (nameChanged) dispatch({ type: 'SET_WORKFLOW_NAME', payload: name })
              if (descriptionChanged) dispatch({ type: 'SET_WORKFLOW_DESCRIPTION', payload: description })
              if (nameChanged || descriptionChanged) markDirty()
            }}
          />
        </FlexItem>
      )}
      {!isNew && (
        <FlexItem flex={{ default: 'flexNone' }}>
          <WorkflowPublishStatusBadge publishedVersionId={publishedVersionId} currentVersionId={currentVersionId} />
        </FlexItem>
      )}
      {!isNew && (
        <FlexItem flex={{ default: 'flexNone' }}>
          <WorkflowReferencedByBadge workflowId={workflowId} />
        </FlexItem>
      )}
      {(builderPermissions.canEdit || isBuiltin) && (
        <FlexItem flex={{ default: 'flexNone' }}>{ProjectSelector}</FlexItem>
      )}
    </Flex>
  )
}
