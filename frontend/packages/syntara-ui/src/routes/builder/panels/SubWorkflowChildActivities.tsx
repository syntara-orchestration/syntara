import {
  Alert,
  Bullseye,
  Button,
  Content,
  ContentVariants,
  ExpandableSection,
  Flex,
  FlexItem,
  Label,
  Spinner,
  Stack,
  StackItem,
} from '@patternfly/react-core'
import { RhUiArrowRightIcon } from '@patternfly/react-icons'
import type { ActivityExecution } from '@syntara/contracts'
import { useNavigate } from '@tanstack/react-router'
import { useState, type ReactNode } from 'react'

import { executionsClient } from '../../../client'
import { SynCodeBlock } from '../../../components/details/SynCodeBlock'
import { formatElapsedTime } from '../../../utils/dateUtils'

import { type ChildExecution, useChildExecutions } from './hooks/useChildExecutions'

type LabelColor = 'green' | 'red' | 'orange' | 'blue' | 'grey' | 'purple'

function statusColor(status: string | null | undefined): LabelColor {
  switch (status ?? '') {
    case 'completed':
      return 'green'
    case 'failed':
    case 'completed_with_errors':
      return 'red'
    case 'cancelled':
      return 'orange'
    case 'running':
      return 'blue'
    default:
      return 'grey'
  }
}

function formatDuration(startedAt: string | null | undefined, completedAt: string | null | undefined): string | null {
  if (!startedAt || !completedAt) return null
  const ms = new Date(completedAt).getTime() - new Date(startedAt).getTime()
  if (!Number.isFinite(ms) || ms < 0) return null
  // Delegate to the shared formatter so child-activity durations use the same
  // units as the rest of the run view, including sub-second (ms) precision.
  return formatElapsedTime(ms)
}

function hasOutput(
  activity: ActivityExecution
): activity is ActivityExecution & { output_data: Record<string, unknown> } {
  return activity.output_data !== null && activity.output_data !== undefined && typeof activity.output_data === 'object'
}

function isTriggerNode(nodeType: string | null | undefined): boolean {
  return typeof nodeType === 'string' && nodeType.endsWith('_trigger')
}

function formatNodeType(nodeType: string | null | undefined): string {
  if (!nodeType) return ''
  if (nodeType === 'subworkflow_trigger') return 'Sub-workflow Trigger'
  if (nodeType === 'sub_workflow') return 'Sub-workflow'
  return nodeType
    .split('_')
    .map((word) => (word ? word.charAt(0).toUpperCase() + word.slice(1) : word))
    .join(' ')
}

function ChildActivityRow({
  activity,
  variant = 'activity',
}: Readonly<{ activity: ActivityExecution; variant?: 'activity' | 'trigger' }>) {
  const [expanded, setExpanded] = useState(false)
  const duration = formatDuration(activity.started_at, activity.completed_at)
  const isTrigger = variant === 'trigger'
  const dataLabel = isTrigger ? 'Received input data' : 'Output data'

  const toggle = (
    <Flex alignItems={{ default: 'alignItemsCenter' }} spaceItems={{ default: 'spaceItemsSm' }}>
      <FlexItem>
        <strong>{activity.activity_name}</strong>
      </FlexItem>
      <FlexItem>
        <Label isCompact color="grey">
          {formatNodeType(activity.node_type)}
        </Label>
      </FlexItem>
      <FlexItem>
        <Label isCompact color={statusColor(activity.status)}>
          {activity.status}
        </Label>
      </FlexItem>
      {duration && (
        <FlexItem>
          <Content component={ContentVariants.small}>{duration}</Content>
        </FlexItem>
      )}
    </Flex>
  )

  let outputContent: ReactNode
  if (hasOutput(activity)) {
    outputContent = <SynCodeBlock jsonObject={activity.output_data} enableCopy enableExpand expandTitle={dataLabel} />
  } else if (activity.error_details) {
    outputContent = null
  } else {
    outputContent = (
      <Content component={ContentVariants.small}>
        {isTrigger ? 'No input recorded for this trigger.' : 'No output for this activity.'}
      </Content>
    )
  }

  return (
    <ExpandableSection
      toggleContent={toggle}
      isExpanded={expanded}
      onToggle={(_e, value) => setExpanded(value)}
      aria-label={`Activity ${activity.activity_name}`}
    >
      {activity.error_details && (
        <Alert
          variant="danger"
          isInline
          isPlain
          title="Error details"
          component="h5"
          style={{ marginBottom: 'var(--pf-t--global--spacer--sm)' }}
        >
          <Content component={ContentVariants.small} style={{ whiteSpace: 'pre-wrap', margin: 0 }}>
            {activity.error_details}
          </Content>
        </Alert>
      )}
      {outputContent}
    </ExpandableSection>
  )
}

function ChildActivitiesList({ childExecutionId }: Readonly<{ childExecutionId: string }>) {
  // Request the maximum page size so a child with many steps is not silently
  // truncated at the default (20). Children beyond 100 activities would need
  // cursor pagination — tracked separately.
  const query = executionsClient.useQuery(
    'get',
    '/executions/{execution_id}/activities',
    { params: { path: { execution_id: childExecutionId }, query: { limit: 100 } } },
    { enabled: Boolean(childExecutionId) }
  )

  if (query.isLoading) {
    return <Spinner size="md" aria-label="Loading child activities" />
  }
  if (query.isError) {
    return <Alert variant="warning" isInline isPlain title="Couldn't load child activities" />
  }

  const activities = query.data?.resources ?? []
  if (activities.length === 0) {
    return <Content component={ContentVariants.small}>No activities recorded for this child yet.</Content>
  }

  // Executable child nodes are the business outputs; subworkflow_trigger (and any
  // other trigger) rows carry the input the child received, shown separately under
  // "Invocation details" so trigger input is not mistaken for a produced output.
  const executable = activities.filter((activity) => !isTriggerNode(activity.node_type))
  const triggers = activities.filter((activity) => isTriggerNode(activity.node_type))

  return (
    <Stack hasGutter>
      {executable.length > 0 ? (
        executable.map((activity) => (
          <StackItem key={activity.id ?? activity.activity_name}>
            <ChildActivityRow activity={activity} />
          </StackItem>
        ))
      ) : (
        <StackItem>
          <Content component={ContentVariants.small}>No executable activities recorded for this child yet.</Content>
        </StackItem>
      )}
      {triggers.length > 0 && (
        <StackItem>
          <ExpandableSection toggleText="Invocation details" aria-label="Invocation details">
            <Stack hasGutter>
              {triggers.map((trigger) => (
                <StackItem key={trigger.id ?? trigger.activity_name}>
                  <ChildActivityRow activity={trigger} variant="trigger" />
                </StackItem>
              ))}
            </Stack>
          </ExpandableSection>
        </StackItem>
      )}
    </Stack>
  )
}

function ChildExecutionSection({ child }: Readonly<{ child: ChildExecution }>) {
  const navigate = useNavigate()
  return (
    <StackItem>
      <Stack hasGutter>
        <StackItem>
          <Flex
            alignItems={{ default: 'alignItemsCenter' }}
            spaceItems={{ default: 'spaceItemsSm' }}
            flexWrap={{ default: 'wrap' }}
          >
            <FlexItem>
              <strong>{child.workflow_name ?? 'Child workflow'}</strong>
            </FlexItem>
            <FlexItem>
              <Label isCompact color={statusColor(child.status)}>
                {child.status}
              </Label>
            </FlexItem>
            {typeof child.workflow_version === 'number' && (
              <FlexItem>
                <Label isCompact color="blue">
                  v{child.workflow_version}
                </Label>
              </FlexItem>
            )}
            <FlexItem grow={{ default: 'grow' }} />
            <FlexItem>
              <Button
                variant="link"
                isInline
                icon={<RhUiArrowRightIcon />}
                iconPosition="end"
                onClick={() => navigate({ to: '/executions/$executionId', params: { executionId: child.id } })}
              >
                View child execution
              </Button>
            </FlexItem>
          </Flex>
          <Content component={ContentVariants.small}>Execution ID: {child.id}</Content>
        </StackItem>
        <StackItem>
          <Content component={ContentVariants.h4}>Child activities</Content>
          <ChildActivitiesList childExecutionId={child.id} />
        </StackItem>
      </Stack>
    </StackItem>
  )
}

/**
 * Execution-view output for a Sub-workflow node: lists each child execution (one
 * per ``for_each`` iteration) with its metadata, a link to the standalone child
 * execution, and its child activities' real ``output_data`` (reused from the
 * existing ``/executions/{id}/activities`` endpoint). No data is duplicated into
 * the parent node's output.
 */
export function SubWorkflowChildActivities({
  parentExecutionId,
  nodeId,
}: Readonly<{ parentExecutionId: string; nodeId: string }>) {
  const { children, isLoading, isError } = useChildExecutions(parentExecutionId, nodeId)

  if (isLoading) {
    return (
      <Bullseye>
        <Spinner aria-label="Loading child executions" />
      </Bullseye>
    )
  }
  if (isError) {
    return <Alert variant="warning" isInline title="Couldn't load the child execution(s)." />
  }
  if (children.length === 0) {
    return (
      <Alert variant="info" isInline isPlain title="No child execution yet">
        <Content component={ContentVariants.small}>
          A child execution appears here once this sub-workflow step has started running.
        </Content>
      </Alert>
    )
  }

  return (
    <Stack hasGutter>
      {children.map((child) => (
        <ChildExecutionSection key={child.id} child={child} />
      ))}
    </Stack>
  )
}
