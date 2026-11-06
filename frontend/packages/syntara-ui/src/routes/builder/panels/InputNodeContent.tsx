import { Alert, Button, Flex, FlexItem, Label, Spinner, Stack, StackItem } from '@patternfly/react-core'
import { RhUiCloseIcon } from '@patternfly/react-icons'
import { ActivityTypeEnum, getNodeOutputSchema, TriggerTypeEnum } from '@syntara/contracts'
import { useMemo } from 'react'

import { useChildWorkflowSchema } from './hooks/useChildWorkflowSchema'
import type { UpstreamNodeInfo } from './hooks/useUpstreamNodes'
import { InputEmptyState } from './InputEmptyState'
import { buildSubWorkflowOutputSchemaTree } from './utils/subWorkflowOutputSchema'
import { getTriggerInputSchemaFields } from './utils/triggerSchemaUtils'
import { InputJsonView } from './views/InputJsonView'
import { InputSchemaPreview } from './views/InputSchemaPreview'
import { InputSchemaView } from './views/InputSchemaView'
import { InputTableView } from './views/InputTableView'
import type { PanelView } from './ViewToggle'

const TRIGGER_TYPES: ReadonlySet<string> = new Set([
  TriggerTypeEnum.MANUAL_TRIGGER,
  TriggerTypeEnum.SCHEDULED,
  TriggerTypeEnum.EVENT,
  TriggerTypeEnum.WEBHOOK_TRIGGER,
  TriggerTypeEnum.EDA_TRIGGER,
])

export type InputNodeContentProps = {
  upstreamNode: UpstreamNodeInfo
  hasData: boolean
  mergedExecutionData: Record<string, Record<string, unknown>> | null
  triggers: { id: string; parameters?: Record<string, unknown> }[] | undefined
  activeView: PanelView
  searchTerm: string
  onRunPreviousSteps?: () => void
  workflowId?: string | null
}

type ChildWorkflowOutputContentProps = Pick<
  InputNodeContentProps,
  'upstreamNode' | 'onRunPreviousSteps' | 'workflowId'
> & {
  expressionNodeId: string
}

function ChildWorkflowOutputStatus({
  childWorkflowId,
  schema,
}: Readonly<{
  childWorkflowId?: string
  schema: ReturnType<typeof useChildWorkflowSchema>
}>) {
  if (!childWorkflowId) {
    return (
      <Alert variant="info" isInline isPlain title="Child workflow not selected">
        Select a child workflow to browse its output fields.
      </Alert>
    )
  }

  if (schema.isLoading) {
    return (
      <Flex alignItems={{ default: 'alignItemsCenter' }} gap={{ default: 'gapSm' }}>
        <FlexItem>
          <Spinner size="sm" aria-label="Loading child workflow outputs" />
        </FlexItem>
        <FlexItem>Loading child workflow outputs</FlexItem>
      </Flex>
    )
  }

  if (schema.isAccessDenied) {
    return (
      <Alert variant="warning" isInline isPlain title="Child step outputs are unavailable">
        You need permission to view the child workflow to browse its step outputs. Aggregate output fields remain
        available.
      </Alert>
    )
  }

  if (schema.isNotFound) {
    return (
      <Alert variant="warning" isInline isPlain title="Published child workflow is unavailable">
        Check that the child workflow has a published version and a Sub-workflow Trigger.
      </Alert>
    )
  }

  if (schema.error) {
    return (
      <Alert variant="danger" isInline title="Unable to load child workflow outputs">
        <Button variant="link" isInline onClick={schema.retry}>
          Retry
        </Button>
      </Alert>
    )
  }

  if (!schema.isEligible) {
    return (
      <Alert variant="warning" isInline isPlain title="Child workflow is not eligible">
        Add a Sub-workflow Trigger to a published child workflow to browse its step outputs.
      </Alert>
    )
  }

  if (schema.needsTriggerSelection) {
    return (
      <Alert variant="info" isInline isPlain title="Select a Sub-workflow Trigger">
        Choose the child trigger in the Sub-workflow step to browse the outputs for that entry point.
      </Alert>
    )
  }

  if (schema.isTriggerUnavailable) {
    return (
      <Alert variant="warning" isInline isPlain title="Selected trigger is unavailable">
        Select a Sub-workflow Trigger that exists in the published child workflow.
      </Alert>
    )
  }

  if (!schema.childSteps.some((step) => (step.outputFields?.length ?? 0) > 0)) {
    return (
      <Alert variant="info" isInline isPlain title="No child step output schemas available">
        The selected trigger has no terminal steps with known output fields.
      </Alert>
    )
  }

  return null
}

function ChildWorkflowOutputContent({
  upstreamNode,
  expressionNodeId,
  onRunPreviousSteps,
  workflowId,
}: Readonly<ChildWorkflowOutputContentProps>) {
  const childSchema = useChildWorkflowSchema({
    workflowId: upstreamNode.childWorkflowId ?? null,
    triggerNodeId: upstreamNode.childTriggerNodeId ?? null,
  })
  const outputTree = useMemo(
    () => buildSubWorkflowOutputSchemaTree(childSchema.isLoading || childSchema.error ? [] : childSchema.childSteps),
    [childSchema.childSteps, childSchema.error, childSchema.isLoading]
  )

  return (
    <Stack hasGutter>
      {onRunPreviousSteps && workflowId && (
        <StackItem>
          <Alert variant="info" isInline isPlain title="Expected input fields">
            <Button variant="link" onClick={onRunPreviousSteps} isInline>
              Run previous steps
            </Button>{' '}
            to see actual values
          </Alert>
        </StackItem>
      )}
      <StackItem>
        <ChildWorkflowOutputStatus childWorkflowId={upstreamNode.childWorkflowId} schema={childSchema} />
      </StackItem>
      <StackItem>
        <InputSchemaPreview tree={outputTree} nodeId={expressionNodeId} />
      </StackItem>
    </Stack>
  )
}

export function InputNodeContent({
  upstreamNode,
  hasData,
  mergedExecutionData,
  triggers,
  activeView,
  searchTerm,
  onRunPreviousSteps,
  workflowId,
}: Readonly<InputNodeContentProps>) {
  const nodeData = hasData ? (mergedExecutionData?.[upstreamNode.id] ?? null) : null
  const expressionNodeId = TRIGGER_TYPES.has(upstreamNode.type) ? 'trigger' : upstreamNode.id

  if (!nodeData) {
    if (upstreamNode.type === ActivityTypeEnum.SUB_WORKFLOW) {
      return (
        <ChildWorkflowOutputContent
          upstreamNode={upstreamNode}
          expressionNodeId={expressionNodeId}
          onRunPreviousSteps={onRunPreviousSteps}
          workflowId={workflowId}
        />
      )
    }

    const schema = getNodeOutputSchema(upstreamNode.type)
    const effectiveSchema = schema ?? getTriggerInputSchemaFields(upstreamNode.id, triggers)
    if (!effectiveSchema) {
      const supportsInputSchema =
        upstreamNode.type === TriggerTypeEnum.MANUAL_TRIGGER ||
        upstreamNode.type === TriggerTypeEnum.WEBHOOK_TRIGGER ||
        upstreamNode.type === TriggerTypeEnum.EDA_TRIGGER
      return <InputEmptyState variant={supportsInputSchema ? 'no-trigger-schema' : 'connected-not-run'} />
    }
    return (
      <Stack hasGutter>
        {onRunPreviousSteps && workflowId && (
          <StackItem>
            <Alert variant="info" isInline isPlain title="Expected input fields">
              <Button variant="link" onClick={onRunPreviousSteps} isInline>
                Run previous steps
              </Button>{' '}
              to see actual values
            </Alert>
          </StackItem>
        )}
        <StackItem>
          <InputSchemaPreview fields={effectiveSchema} nodeId={expressionNodeId} />
        </StackItem>
      </Stack>
    )
  }

  switch (activeView) {
    case 'schema':
      return (
        <InputSchemaView
          data={nodeData}
          nodeId={expressionNodeId}
          searchTerm={searchTerm}
          hierarchical={upstreamNode.type === ActivityTypeEnum.SUB_WORKFLOW ? true : undefined}
        />
      )
    case 'table':
      return <InputTableView data={nodeData} searchTerm={searchTerm} />
    case 'json':
      return <InputJsonView data={nodeData} />
    default: {
      const _exhaustive: never = activeView
      return _exhaustive
    }
  }
}

export type InputPanelNodeSectionProps = {
  upstreamNode: UpstreamNodeInfo
  hasPinnedMock: boolean
  handleUnpinSingle: (nodeId: string) => void
  children: React.ReactNode
}

export function InputPanelNodeSection({
  upstreamNode,
  hasPinnedMock,
  handleUnpinSingle,
  children,
}: Readonly<InputPanelNodeSectionProps>) {
  return (
    <Flex direction={{ default: 'column' }} spaceItems={{ default: 'spaceItemsSm' }}>
      {hasPinnedMock && (
        <FlexItem>
          <Flex alignItems={{ default: 'alignItemsCenter' }}>
            <FlexItem>
              <Label color="grey" isCompact>
                Mock data pinned
              </Label>
            </FlexItem>
            <FlexItem>
              <Button variant="link" isDanger onClick={() => handleUnpinSingle(upstreamNode.id)}>
                <RhUiCloseIcon /> Unpin data
              </Button>
            </FlexItem>
          </Flex>
        </FlexItem>
      )}
      <FlexItem>{children}</FlexItem>
    </Flex>
  )
}
