import { Content, ContentVariants } from '@patternfly/react-core'
import { TriggerTypeEnum } from '@syntara/contracts'
import { type Node, type NodeProps } from '@xyflow/react'
import type { CSSProperties } from 'react'

import { SynStep } from '../../../../components/steps/SynStep'
import { SynStepBody } from '../../../../components/steps/SynStepBody'
import { FlowNodeType } from '../../../../constants'
import { parseTriggerIndex } from '../../../../utils/triggerNodeIds'
import type { ActivityStatus } from '../../execution/types'
import { semanticZoomActivityTitle } from '../semanticZoom'
import { getStepTypeColor } from '../stepTypeColors'

import { StandardStepHeader } from './common/StandardStepHeader'
import { StepMenuCategory, useStepMenuActions } from './hooks/useStepMenuActions'
import { renderStepIcon } from './renderStepIcon'
import { stepMetadata } from './stepMetadata'

export type TriggerNode = { type: 'trigger' } & Node<{
  name: string
  details: string | null
  triggerType?: string
  config?: Record<string, unknown>
}>

export function TriggerStepComponent(props: NodeProps<TriggerNode>) {
  const triggerName = props.data.name
  const triggerDetails = props.data.details
  const triggerType = props.data.triggerType
  const isScheduled = triggerType === TriggerTypeEnum.SCHEDULED
  const isWebhook = triggerType === TriggerTypeEnum.WEBHOOK_TRIGGER
  const isEda = triggerType === TriggerTypeEnum.EDA_TRIGGER

  let metadata = stepMetadata.trigger
  let iconId = 'trigger-manual'
  if (isScheduled) {
    metadata = stepMetadata.scheduledTrigger
    iconId = 'trigger-scheduled'
  } else if (isWebhook) {
    metadata = stepMetadata.webhookTrigger
    iconId = 'trigger-webhook'
  } else if (isEda) {
    metadata = stepMetadata.edaTrigger
    iconId = 'trigger-eda'
  }
  const iconColor = getStepTypeColor(FlowNodeType.TRIGGER)
  const iconNode = renderStepIcon(metadata.icon, iconId, 'canvas', iconColor)
  const semanticZoomIcon = renderStepIcon(metadata.icon, iconId, 'semanticZoom', iconColor)
  const triggerStyle: CSSProperties = {
    borderTopLeftRadius: '45px',
    borderBottomLeftRadius: '45px',
    borderTopRightRadius: 'var(--pf-t--global--border--radius--medium)',
    borderBottomRightRadius: 'var(--pf-t--global--border--radius--medium)',
    paddingLeft: 'var(--pf-t--global--spacer--lg)',
  }

  const triggerIndex = parseTriggerIndex(props.id) ?? 0
  const menuActions = useStepMenuActions({
    nodeId: props.id,
    stepCategory: StepMenuCategory.TRIGGER,
    triggerIndex,
  })

  const executionState = (props.data as Record<string, unknown>).__executionState as
    | {
        status: ActivityStatus
        started_at?: string
        completed_at?: string
        error_details?: string
        retry_count?: number
      }
    | undefined

  const showExecutionBadge =
    ((props.data as Record<string, unknown>).metadata as { __showExecutionBadge?: boolean } | undefined)
      ?.__showExecutionBadge === true

  let triggerTypeLabel = 'Manual trigger'
  if (isScheduled) {
    triggerTypeLabel = 'Scheduled trigger'
  } else if (isWebhook) {
    triggerTypeLabel = 'Webhook trigger'
  } else if (isEda) {
    triggerTypeLabel = 'Event-Driven Ansible trigger'
  }

  return (
    <SynStep
      disableTarget={metadata.disableTarget}
      className={metadata.className}
      nodeProps={props}
      style={triggerStyle}
      collapsible={false}
      executionState={executionState}
      showExecutionBadge={showExecutionBadge}
      topBarColor={getStepTypeColor(FlowNodeType.TRIGGER)}
      semanticZoomSummary={{
        title: semanticZoomActivityTitle(triggerName, `Untitled ${metadata.label}`),
        typeLabel: triggerTypeLabel,
      }}
      semanticZoomIcon={semanticZoomIcon}
      semanticZoomPreviewIcon={iconNode}
      semanticZoomMenuActions={menuActions}
      semanticZoomExpandable={metadata.expandable}
    >
      <TriggerStepDetails
        icon={iconNode}
        menuActions={menuActions}
        triggerName={triggerName}
        triggerDetails={triggerDetails}
        triggerKind={props.data.triggerType}
      />
    </SynStep>
  )
}

function TriggerStepDetails(
  props: Readonly<{
    icon?: React.ReactNode
    menuActions?: ReturnType<typeof useStepMenuActions>
    triggerName: string
    triggerDetails: string | null
    triggerKind?: string
  }>
) {
  const isScheduledTrigger = props.triggerKind === TriggerTypeEnum.SCHEDULED
  const isWebhookTrigger = props.triggerKind === TriggerTypeEnum.WEBHOOK_TRIGGER
  const isEdaTrigger = props.triggerKind === TriggerTypeEnum.EDA_TRIGGER
  const normalizedDetails = props.triggerDetails ?? null

  let triggerTypeLabel = 'Manual trigger'
  if (isScheduledTrigger) {
    triggerTypeLabel = 'Scheduled trigger'
  } else if (isWebhookTrigger) {
    triggerTypeLabel = 'Webhook trigger'
  } else if (isEdaTrigger) {
    triggerTypeLabel = 'Event-Driven Ansible trigger'
  }

  return (
    <>
      <StandardStepHeader
        icon={props.icon}
        title={props.triggerName}
        subtitle={triggerTypeLabel}
        menuActions={props.menuActions}
        expandable={false}
      />
      <SynStepBody>
        {normalizedDetails ? (
          <Content component={ContentVariants.small} style={{ whiteSpace: 'pre-line', overflowWrap: 'anywhere' }}>
            {normalizedDetails}
          </Content>
        ) : null}
      </SynStepBody>
    </>
  )
}
