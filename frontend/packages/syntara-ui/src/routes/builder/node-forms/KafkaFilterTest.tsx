import { Alert, Button, Content, Stack, StackItem } from '@patternfly/react-core'
import { useFormContext } from 'react-hook-form'

import { filteringClient } from '../../../client'
import { SynErrorState } from '../../../components/states/SynErrorState'
import { detachPromise } from '../../../utils/detachPromise'

import { filterConfigurationError } from './filterConfigurationError'
import type { TriggerFormData } from './triggerFormSchema'

const OUTCOME_TITLES = { match: 'Match', no_match: 'No match', evaluation_error: 'Evaluation error' } as const

/** Remounted for every expression/sample change so in-flight responses cannot describe new input. */
export function KafkaFilterTest({
  expression,
  sample,
  validateSample,
}: Readonly<{
  expression: string
  sample: string
  validateSample: () => Promise<boolean>
}>) {
  const { setError } = useFormContext<TriggerFormData>()
  const mutation = filteringClient.useMutation('post', '/filtering/test')
  const error = mutation.error
  const configurationMessage = filterConfigurationError(error)
  const resultVariant = mutation.data?.outcome === 'match' ? 'success' : 'info'

  const testFilter = async () => {
    if (!(await validateSample()) || Array.from(expression).length > 16_384) return
    const input: unknown = JSON.parse(sample)
    mutation.mutate(
      { body: { expression, input } },
      {
        onError: (problem) => {
          const message = filterConfigurationError(problem)
          if (message) setError('filterExpression', { type: 'server', message })
        },
      }
    )
  }

  return (
    <Stack hasGutter>
      <StackItem aria-live="polite" aria-atomic>
        {mutation.isPending && <Content component="p">Testing filter…</Content>}
        {configurationMessage && (
          <Alert variant="danger" isInline title="Filter configuration error" component="h4">
            Check the CEL expression for errors and try again. {configurationMessage}
          </Alert>
        )}
        {mutation.isError && !configurationMessage && (
          <SynErrorState
            title="Filter test request failed"
            message={error}
            onRetry={() => detachPromise(testFilter())}
          />
        )}
        {mutation.data && (
          <Alert
            variant={mutation.data.outcome === 'evaluation_error' ? 'warning' : resultVariant}
            isInline
            title={OUTCOME_TITLES[mutation.data.outcome]}
            component="h4"
          >
            {mutation.data.outcome === 'evaluation_error' ? (
              `The expression could not evaluate to a boolean for this sample. Error code: ${mutation.data.error_code ?? 'filter_evaluation_failed'}`
            ) : (
              <Content component="p">
                {mutation.data.outcome === 'match'
                  ? 'This sample message passes the filter.'
                  : 'This sample message does not pass the filter.'}
              </Content>
            )}
          </Alert>
        )}
      </StackItem>
      <StackItem>
        <Button
          variant="secondary"
          isDisabled={mutation.isPending || Array.from(expression).length > 16_384}
          isLoading={mutation.isPending}
          onClick={() => detachPromise(testFilter())}
        >
          Test filter
        </Button>
      </StackItem>
      <StackItem>
        <Content component="p">
          Test the unsaved expression without saving or selecting Kafka resources. This is separate from Test runtime
          access. Sample testing does not consume Kafka messages, validate the payload schema, or trigger workflows. One
          successful sample does not guarantee successful evaluation for every message. Saving and publication still use
          server validation.
        </Content>
      </StackItem>
    </Stack>
  )
}
