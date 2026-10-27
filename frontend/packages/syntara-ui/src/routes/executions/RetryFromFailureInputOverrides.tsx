import {
  Alert,
  Content,
  ContentVariants,
  ExpandableSection,
  FormGroup,
  FormHelperText,
  HelperText,
  HelperTextItem,
  Spinner,
  Stack,
  StackItem,
  TextArea,
  Title,
} from '@patternfly/react-core'
import type { ChangeEvent } from 'react'
import { useId, useState } from 'react'

import { executionsClient } from '../../client'

import styles from './RetryFromFailureInputOverrides.module.css'
import type { RetryInputOverrideTarget } from './retryInputOverrides'

type RetryFromFailureInputOverridesProps = Readonly<{
  executionId: string
  targets: RetryInputOverrideTarget[]
  workflowDefinitionAvailable: boolean
  isDisabled: boolean
  drafts: Readonly<Record<string, string>>
  onDraftChange: (
    nodeId: string,
    value: string,
    parsed: Record<string, unknown> | undefined,
    error: string | undefined
  ) => void
}>

/** Optional per-failure parameter overrides for one retry request. */
export function RetryFromFailureInputOverrides({
  executionId,
  targets,
  workflowDefinitionAvailable,
  isDisabled,
  drafts,
  onDraftChange,
}: RetryFromFailureInputOverridesProps) {
  const [isExpanded, setIsExpanded] = useState(false)

  if (targets.length === 0) {
    const message = workflowDefinitionAvailable
      ? 'No selected failed steps have configurable input parameters to override.'
      : 'Input overrides are unavailable because this run’s workflow definition could not be loaded.'
    return <Content component={ContentVariants.small}>{message}</Content>
  }

  return (
    <ExpandableSection
      toggleText="Change inputs before retry"
      isExpanded={isExpanded}
      onToggle={(_event, expanded) => setIsExpanded(expanded)}
    >
      {isExpanded && (
        <Stack hasGutter>
          <StackItem>
            <Content component={ContentVariants.small}>
              Overrides apply to this retry only. Enter a JSON object containing only the parameters you want to change;
              leave it as <code>{'{}'}</code> to keep the original inputs. For loop nodes, an override applies each time
              the node runs during the retry.
            </Content>
          </StackItem>
          {targets.map((target) => (
            <StackItem key={target.id}>
              <RetryInputOverrideEditor
                executionId={executionId}
                target={target}
                isDisabled={isDisabled}
                draft={drafts[target.id] ?? '{}'}
                onDraftChange={onDraftChange}
              />
            </StackItem>
          ))}
        </Stack>
      )}
    </ExpandableSection>
  )
}

function RetryInputOverrideEditor({
  executionId,
  target,
  isDisabled,
  draft,
  onDraftChange,
}: Readonly<{
  executionId: string
  target: RetryInputOverrideTarget
  isDisabled: boolean
  draft: string
  onDraftChange: RetryFromFailureInputOverridesProps['onDraftChange']
}>) {
  const fieldId = useId()
  const failedActivityName = target.failedActivityName ?? target.id
  const activityQuery = executionsClient.useQuery(
    'get',
    '/executions/{execution_id}/activities',
    {
      params: {
        path: { execution_id: executionId },
        query: {
          activity_name: failedActivityName,
          status: 'failed',
          limit: 1,
          sort: '-created_at',
        },
      },
    },
    { retry: false }
  )

  const activityInput = activityQuery.data?.resources?.[0]?.input_data
  const visibleInputs = activityInput
    ? Object.fromEntries(
        target.parameterNames.filter((key) => key in activityInput).map((key) => [key, activityInput[key]])
      )
    : undefined
  const { error } = parseOverrideDraft(draft, target.parameterNames)
  const helperTextId = `${fieldId}-helper-text`

  function renderPreviousInputs() {
    if (activityQuery.isPending) {
      return <Spinner size="sm" aria-label={`Loading inputs for ${target.name}`} />
    }
    if (activityQuery.isError) {
      return (
        <Alert isInline variant="warning" title="Could not load the previous inputs">
          You can still enter the parameter values to override below.
        </Alert>
      )
    }
    if (visibleInputs && Object.keys(visibleInputs).length > 0) {
      return <pre className={styles.inputPreview}>{JSON.stringify(visibleInputs, null, 2)}</pre>
    }
    return <Content component={ContentVariants.small}>No previous input values are available for this step.</Content>
  }

  const handleChange = (_event: ChangeEvent<HTMLTextAreaElement>, value: string) => {
    const result = parseOverrideDraft(value, target.parameterNames)
    onDraftChange(target.id, value, result.parsed, result.error)
  }

  return (
    <Stack hasGutter className={styles.nodeEditor}>
      <StackItem>
        <Title headingLevel="h4">{target.name}</Title>
      </StackItem>
      <StackItem>
        <Title headingLevel="h5">Inputs from the most recent failed attempt</Title>
        {renderPreviousInputs()}
      </StackItem>
      <StackItem>
        <FormGroup label="Parameters to override (JSON)" fieldId={`${fieldId}-override`}>
          <TextArea
            id={`${fieldId}-override`}
            aria-label={`Parameters to override for ${target.name}`}
            aria-describedby={helperTextId}
            value={draft}
            onChange={handleChange}
            isDisabled={isDisabled}
            resizeOrientation="vertical"
            rows={5}
            validated={error ? 'error' : 'default'}
          />
          <FormHelperText>
            <HelperText isLiveRegion>
              <HelperTextItem id={helperTextId} variant={error ? 'error' : 'default'}>
                {error ?? `Allowed parameters: ${target.parameterNames.join(', ')}. Values must be valid JSON.`}
              </HelperTextItem>
            </HelperText>
          </FormHelperText>
        </FormGroup>
      </StackItem>
    </Stack>
  )
}

function parseOverrideDraft(
  value: string,
  allowedParameterNames: string[]
): { parsed: Record<string, unknown> | undefined; error: string | undefined } {
  let parsedValue: unknown
  try {
    parsedValue = JSON.parse(value)
  } catch {
    return { parsed: undefined, error: 'Enter a valid JSON object.' }
  }

  if (parsedValue === null || typeof parsedValue !== 'object' || Array.isArray(parsedValue)) {
    return { parsed: undefined, error: 'Enter a JSON object of parameter names and values.' }
  }

  const parsed = parsedValue as Record<string, unknown>
  const unknownParameters = Object.keys(parsed).filter((key) => !allowedParameterNames.includes(key))
  if (unknownParameters.length > 0) {
    return {
      parsed: undefined,
      error: `Unknown parameter${unknownParameters.length === 1 ? '' : 's'}: ${unknownParameters.join(', ')}.`,
    }
  }

  return { parsed: Object.keys(parsed).length > 0 ? parsed : undefined, error: undefined }
}
