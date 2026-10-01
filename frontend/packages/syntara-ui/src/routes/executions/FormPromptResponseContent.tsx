import {
  Alert,
  Button,
  DescriptionList,
  DescriptionListDescription,
  DescriptionListGroup,
  DescriptionListTerm,
  Divider,
  Spinner,
  Stack,
  StackItem,
} from '@patternfly/react-core'
import type { FormsAPI } from '@syntara/contracts'
import { useQueryClient } from '@tanstack/react-query'

import { formsClient } from '../../client'
import { SynCodeBlock } from '../../components/details/SynCodeBlock'
import { DisabledWithTooltip } from '../../components/DisabledWithTooltip'
import { SynDynamicForm } from '../../components/forms/SynDynamicForm'
import { SynEmptyStateAccessDenied } from '../../components/states/SynEmptyStateAccessDenied'
import { useQueryState } from '../../components/states/useQueryState'
import { useMutationErrorHandler } from '../../hooks/useMutationErrorHandler'
import { useAlerts } from '../../providers/alerts'
import { detachPromise } from '../../utils/detachPromise'
import { useExecutionStore } from '../workflows/stores/useExecutionStore'

import {
  canvasNodeIdFromPromptNodeId,
  lookupMapByPromptNodeId,
  resolveFormPromptWaitingStartedAt,
} from './formPrompt/formPromptNodeId'
import styles from './FormPromptResponseContent.module.css'
import { FormPromptRunningLongAlert, FormPromptWaitingDuration } from './FormPromptTimeoutIndicators'
import { useCanSubmitFormPrompt } from './hooks/useCanSubmitFormPrompt'
import { useFormPromptPermissions } from './hooks/useFormPromptPermissions'

type FormPromptRead = FormsAPI.components['schemas']['FormPromptRead']

function formPromptResponseFormId(formPromptId: string): string {
  return `form-prompt-response-${formPromptId}`
}

type FormPromptResponseContentProps = Readonly<{
  executionId: string
  formPromptId: string
  activityNameMap?: Map<string, string>
  onSubmitted?: () => void
}>

function isFormPromptRead(data: unknown): data is FormPromptRead {
  return typeof data === 'object' && data !== null && 'form_definition' in data
}

function resolvePromptStepLabel(prompt: FormPromptRead, activityNameMap?: Map<string, string>): string {
  return (
    lookupMapByPromptNodeId(activityNameMap, prompt.prompt_node_id) ??
    canvasNodeIdFromPromptNodeId(prompt.prompt_node_id) ??
    prompt.name
  )
}

function SubmittedDataReadOnly({ data }: Readonly<{ data: Record<string, unknown> }>) {
  return (
    <DescriptionList isCompact isHorizontal>
      {Object.entries(data).map(([key, value]) => (
        <DescriptionListGroup key={key}>
          <DescriptionListTerm>{key}</DescriptionListTerm>
          <DescriptionListDescription>
            {typeof value === 'string' ? value : <SynCodeBlock>{JSON.stringify(value, null, 2)}</SynCodeBlock>}
          </DescriptionListDescription>
        </DescriptionListGroup>
      ))}
    </DescriptionList>
  )
}

function getSubmitTooltip(
  permissions: ReturnType<typeof useFormPromptPermissions>,
  canSubmitAsResponder: boolean
): string | undefined {
  if (!permissions.canSubmit) {
    return permissions.tooltips.submit
  }
  if (!canSubmitAsResponder) {
    return 'You are not configured as a responder for this form.'
  }
  return undefined
}

function FormPromptSummary({
  promptStepLabel,
  message,
  waitingStartedAt,
  isPending,
}: Readonly<{
  promptStepLabel: string
  message?: string | null
  waitingStartedAt?: string | null
  isPending: boolean
}>) {
  return (
    <DescriptionList>
      <DescriptionListGroup>
        <DescriptionListTerm>Prompt step</DescriptionListTerm>
        <DescriptionListDescription>{promptStepLabel}</DescriptionListDescription>
      </DescriptionListGroup>
      {isPending && waitingStartedAt ? (
        <DescriptionListGroup>
          <DescriptionListTerm>Waiting</DescriptionListTerm>
          <DescriptionListDescription>
            <FormPromptWaitingDuration waitingStartedAt={waitingStartedAt} isPending={isPending} />
          </DescriptionListDescription>
        </DescriptionListGroup>
      ) : null}
      {message ? (
        <DescriptionListGroup>
          <DescriptionListTerm>Message</DescriptionListTerm>
          <DescriptionListDescription className={styles.message}>{message}</DescriptionListDescription>
        </DescriptionListGroup>
      ) : null}
    </DescriptionList>
  )
}

function FormPromptResponseBody({
  prompt,
  activityNameMap,
  isPending,
  canSubmit,
  submitTooltip,
  submitMutation,
  onSubmit,
}: Readonly<{
  prompt: FormPromptRead
  activityNameMap?: Map<string, string>
  isPending: boolean
  canSubmit: boolean
  submitTooltip: string | undefined
  submitMutation: { isPending: boolean }
  onSubmit: (responseData: Record<string, unknown>) => Promise<void>
}>) {
  const promptStepLabel = resolvePromptStepLabel(prompt, activityNameMap)
  const responseFormId = formPromptResponseFormId(prompt.id ?? 'form-prompt')
  const submitLabel = prompt.submit_label ?? 'Submit'
  const submitDisabled = !canSubmit || submitMutation.isPending
  const activityStates = useExecutionStore((state) => state.activityStates)
  const waitingStartedAt = resolveFormPromptWaitingStartedAt(prompt, activityStates)

  return (
    <Stack hasGutter className={styles.outerStack}>
      <StackItem isFilled className={styles.scrollableBody}>
        <Stack hasGutter>
          <StackItem>
            <FormPromptSummary
              promptStepLabel={promptStepLabel}
              message={prompt.message}
              waitingStartedAt={waitingStartedAt}
              isPending={isPending}
            />
          </StackItem>
          {isPending ? (
            <StackItem>
              <FormPromptRunningLongAlert
                waitingStartedAt={waitingStartedAt}
                timeoutAt={prompt.timeout_at}
                isPending={isPending}
              />
            </StackItem>
          ) : null}
          {prompt.status === 'submitted' && prompt.response_data ? (
            <StackItem>
              <DescriptionList>
                <DescriptionListGroup>
                  <DescriptionListTerm>Submitted response</DescriptionListTerm>
                  <DescriptionListDescription>
                    <SubmittedDataReadOnly data={prompt.response_data} />
                  </DescriptionListDescription>
                </DescriptionListGroup>
              </DescriptionList>
            </StackItem>
          ) : null}
          {prompt.status !== 'pending' && prompt.status !== 'submitted' ? (
            <StackItem>
              <Alert variant="info" isInline title="Form prompt closed">
                This prompt is no longer accepting responses ({prompt.status}).
              </Alert>
            </StackItem>
          ) : null}
          {isPending ? (
            <StackItem>
              <SynDynamicForm
                id={responseFormId}
                definition={prompt.form_definition}
                submitLabel={submitLabel}
                isDisabled={submitDisabled}
                isReadOnly={!canSubmit}
                hideSubmitButton
                onSubmit={onSubmit}
              />
            </StackItem>
          ) : null}
        </Stack>
      </StackItem>

      {isPending && canSubmit ? (
        <StackItem className={styles.footer}>
          <Stack hasGutter>
            <StackItem>
              <Divider />
            </StackItem>
            <StackItem>
              <DisabledWithTooltip isDisabled={submitDisabled} content={submitTooltip}>
                <Button
                  type="submit"
                  form={responseFormId}
                  variant="primary"
                  isDisabled={submitDisabled}
                  isLoading={submitMutation.isPending}
                >
                  {submitLabel}
                </Button>
              </DisabledWithTooltip>
            </StackItem>
          </Stack>
        </StackItem>
      ) : null}
    </Stack>
  )
}

export function FormPromptResponseContent({
  executionId,
  formPromptId,
  activityNameMap,
  onSubmitted,
}: FormPromptResponseContentProps) {
  const queryClient = useQueryClient()
  const { showSuccess } = useAlerts()
  const submitMutation = formsClient.useMutation('post', '/form_prompts/{form_prompt_id}/submit')
  const handleMutationError = useMutationErrorHandler()

  const promptQuery = formsClient.useQuery('get', '/form_prompts/{form_prompt_id}', {
    params: { path: { form_prompt_id: formPromptId } },
  })

  const prompt = isFormPromptRead(promptQuery.data) ? promptQuery.data : undefined
  const promptExecutionMismatch =
    prompt !== undefined && prompt.execution_id.toLowerCase() !== executionId.toLowerCase()

  const permissions = useFormPromptPermissions(prompt?.project_id)
  const {
    canSubmit: canSubmitAsResponder,
    isLoading: isCheckingResponder,
    isError: isResponderCheckError,
  } = useCanSubmitFormPrompt(prompt)

  const queryState = useQueryState(promptQuery, {
    title: 'Error loading form prompt',
    onRetry: () => detachPromise(promptQuery.refetch()),
  })

  if (queryState) {
    return queryState
  }

  if (promptQuery.isLoading || !prompt) {
    return <Spinner aria-label="Loading form prompt" />
  }

  if (promptExecutionMismatch) {
    return (
      <Alert variant="danger" isInline title="Form prompt unavailable">
        This form prompt belongs to a different workflow run.
      </Alert>
    )
  }

  if (permissions.isChecking || isCheckingResponder) {
    return <Spinner aria-label="Checking permissions" />
  }

  if (permissions.isError || isResponderCheckError) {
    return (
      <Alert
        variant="danger"
        isInline
        title="Could not verify permissions"
        actionLinks={
          <Button variant="link" isInline onClick={() => detachPromise(promptQuery.refetch())}>
            Retry
          </Button>
        }
      >
        Authorization checks failed. Try again in a moment.
      </Alert>
    )
  }

  if (!permissions.canRead) {
    return (
      <SynEmptyStateAccessDenied description="You do not have permission to view this form prompt. Contact your administrator to request access." />
    )
  }

  const isPending = prompt.status === 'pending'
  const canSubmit = permissions.canSubmit && canSubmitAsResponder && isPending && !isCheckingResponder
  const submitTooltip = getSubmitTooltip(permissions, canSubmitAsResponder)

  const handleSubmit = async (responseData: Record<string, unknown>) => {
    try {
      await submitMutation.mutateAsync({
        params: { path: { form_prompt_id: formPromptId } },
        body: { response_data: responseData },
      })
      showSuccess({ title: 'Form submitted', description: prompt.success_message ?? 'Your response was recorded.' })
      await Promise.all([
        queryClient.refetchQueries({ queryKey: ['get', '/executions/{execution_id}'] }),
        queryClient.refetchQueries({ queryKey: ['get', '/form_prompts'] }),
        queryClient.refetchQueries({ queryKey: ['get', '/form_prompts/{form_prompt_id}'] }),
      ])
      await promptQuery.refetch()
      onSubmitted?.()
    } catch (error) {
      handleMutationError({ title: 'Failed to submit form' })(error)
    }
  }

  return (
    <FormPromptResponseBody
      prompt={prompt}
      activityNameMap={activityNameMap}
      isPending={isPending}
      canSubmit={canSubmit}
      submitTooltip={submitTooltip}
      submitMutation={submitMutation}
      onSubmit={handleSubmit}
    />
  )
}
