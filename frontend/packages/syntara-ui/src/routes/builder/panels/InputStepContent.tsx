import { Alert, Button, Flex, FlexItem, Label, Stack, StackItem } from '@patternfly/react-core'
import { RhUiCloseIcon } from '@patternfly/react-icons'
import { getNodeOutputSchema, TriggerTypeEnum } from '@syntara/contracts'

import type { UpstreamStepInfo } from './hooks/useUpstreamSteps'
import { InputEmptyState } from './InputEmptyState'
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

export type InputStepContentProps = {
  upstreamNode: UpstreamStepInfo
  hasData: boolean
  mergedExecutionData: Record<string, Record<string, unknown>> | null
  triggers: { id: string; parameters?: Record<string, unknown> }[] | undefined
  activeView: PanelView
  searchTerm: string
  onRunPreviousSteps?: () => void
  workflowId?: string | null
}

export function InputStepContent({
  upstreamNode,
  hasData,
  mergedExecutionData,
  triggers,
  activeView,
  searchTerm,
  onRunPreviousSteps,
  workflowId,
}: Readonly<InputStepContentProps>) {
  const nodeData = hasData ? (mergedExecutionData?.[upstreamNode.id] ?? null) : null
  const expressionNodeId = TRIGGER_TYPES.has(upstreamNode.type) ? 'trigger' : upstreamNode.id

  if (!nodeData) {
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
      return <InputSchemaView data={nodeData} nodeId={expressionNodeId} searchTerm={searchTerm} />
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

export type InputPanelStepSectionProps = {
  upstreamNode: UpstreamStepInfo
  hasPinnedMock: boolean
  handleUnpinSingle: (nodeId: string) => void
  children: React.ReactNode
}

export function InputPanelStepSection({
  upstreamNode,
  hasPinnedMock,
  handleUnpinSingle,
  children,
}: Readonly<InputPanelStepSectionProps>) {
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
