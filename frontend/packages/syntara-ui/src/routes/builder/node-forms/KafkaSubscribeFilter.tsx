import { Content, ExpandableSection, Stack, StackItem, TextArea } from '@patternfly/react-core'
import { use, useState } from 'react'
import { useForm, useFormContext, useWatch } from 'react-hook-form'
import { z } from 'zod'

import { FieldHelpPopover } from '../../../components/FieldHelpPopover'
import { FormFieldError } from '../../../components/FormFieldError'
import { SynFormField } from '../../../components/forms/SynFormField'
import { useDocLink } from '../../../utils/docs/useDocLink'
import { ExpandableCodeEditor } from '../components/ExpandableCodeEditor'
import { WorkflowValidationContext } from '../WorkflowValidationContext'

import { KafkaFilterTest } from './KafkaFilterTest'
import { hasKafkaFilterExpression } from './kafkaSubscribeMapping'
import { zodResolver } from './shared/formSchemaUtils'
import type { TriggerFormData } from './triggerFormSchema'

const SAMPLE_HINT =
  'The sample is bound directly as input, without a wrapper or Kafka decoding. Edit this Kafka-shaped example to try different messages.'

const sampleSchema = z.object({
  sample: z.string().refine((value) => {
    try {
      JSON.parse(value)
      return true
    } catch {
      return false
    }
  }, 'Enter valid JSON before testing the filter'),
})

const EXAMPLE_INPUT = JSON.stringify(
  {
    key: { kind: 'text', text: 'order-42', base64: 'b3JkZXItNDI=' },
    headers: {
      region: [
        { kind: 'text', text: 'us', base64: 'dXM=' },
        { kind: 'text', text: 'eu', base64: 'ZXU=' },
      ],
    },
    metadata: {
      transport: 'kafka',
      topic: 'orders',
      partition: 0,
      offset: '42',
      timestamp_ms: null,
      timestamp_type: null,
    },
    payload: { state: 'decoded', value: { status: 'ready', total: 125 }, error_code: null },
    cloudevents: null,
  },
  null,
  2
)

export function KafkaSubscribeFilter({ isReadOnly }: Readonly<{ isReadOnly: boolean }>) {
  const docsUrl = useDocLink('kafkaSubscribeTrigger')
  const validation = use(WorkflowValidationContext)
  const { control, setValue, clearErrors } = useFormContext<TriggerFormData>()
  const expression = useWatch({ control, name: 'filterExpression' }) ?? ''
  const [isTesting, setTesting] = useState(false)
  const workflowError = validation.errors.find(
    (error) =>
      error.nodeId === validation.nodeId &&
      error.fieldPath === 'parameters.filter.expression' &&
      error.filterExpression === expression
  )?.message
  const sampleForm = useForm({
    resolver: zodResolver(sampleSchema, undefined, { mode: 'sync' }),
    defaultValues: { sample: EXAMPLE_INPUT },
    mode: 'onChange',
  })
  const sample = useWatch({ control: sampleForm.control, name: 'sample' })
  const hasFilter = hasKafkaFilterExpression(expression)

  return (
    <Stack hasGutter>
      <StackItem>
        <SynFormField<TriggerFormData, 'filterExpression'>
          name="filterExpression"
          label="Filter expression (CEL)"
          fieldId="kafka-filter-expression"
          labelHelp={
            <FieldHelpPopover
              headerContent="Filter expression (CEL)"
              helpText={
                <Content component="p">
                  Write a CEL condition against input, the Kafka message object, for example{' '}
                  <code>input.key.text.startsWith("order-")</code>. Return true to pass a message or false to filter it
                  out. See the{' '}
                  <a href={docsUrl} target="_blank" rel="noreferrer">
                    Kafka Subscribe documentation
                  </a>{' '}
                  for available fields, syntax, and more examples.
                </Content>
              }
            />
          }
          hint={`${Array.from(expression).length.toLocaleString()} / 16,384 characters. ${hasFilter ? 'Enter a CEL condition that returns true or false.' : 'No filter: every otherwise valid message is accepted.'} Leave empty to disable CEL filtering.`}
        >
          {({ field, fieldState, describedBy }) => (
            <TextArea
              id="kafka-filter-expression"
              name={field.name}
              value={field.value ?? ''}
              onChange={(_event, value) => {
                clearErrors('filterExpression')
                setValue('filterExpression', value, { shouldDirty: true, shouldValidate: true })
              }}
              onBlur={field.onBlur}
              ref={field.ref}
              readOnly={isReadOnly}
              rows={5}
              validated={(fieldState.error ?? workflowError) ? 'error' : 'default'}
              aria-invalid={Boolean(fieldState.error ?? workflowError)}
              aria-describedby={workflowError && !fieldState.error ? 'kafka-filter-workflow-error' : describedBy}
              spellCheck={false}
            />
          )}
        </SynFormField>
        {workflowError && <FormFieldError id="kafka-filter-workflow-error" message={workflowError} />}
      </StackItem>
      {!isReadOnly && (
        <StackItem>
          <ExpandableSection
            toggleText={isTesting ? 'Hide filter test' : 'Test filter expression'}
            isExpanded={isTesting}
            onToggle={(_event, expanded) => setTesting(expanded)}
          >
            {isTesting && (
              <Stack hasGutter>
                <StackItem>
                  <SynFormField
                    name="sample"
                    control={sampleForm.control}
                    label="Sample JSON"
                    fieldId="kafka-filter-sample"
                    hint={SAMPLE_HINT}
                  >
                    {({ field, fieldState, describedBy }) => (
                      <div
                        id="kafka-filter-sample"
                        role="group"
                        aria-label="Sample JSON"
                        aria-describedby={describedBy}
                      >
                        <ExpandableCodeEditor
                          code={field.value}
                          onCodeChange={field.onChange}
                          onBlur={field.onBlur}
                          ref={(editor) => field.ref(editor)}
                          language="json"
                          height="240px"
                          modalTitle="Edit sample JSON"
                          ariaLabel="Sample JSON"
                          ariaDescribedBy={describedBy}
                          description={fieldState.error?.message ?? SAMPLE_HINT}
                        />
                      </div>
                    )}
                  </SynFormField>
                </StackItem>
                <StackItem>
                  <KafkaFilterTest
                    key={JSON.stringify([expression, sample])}
                    expression={expression}
                    sample={sample}
                    validateSample={() => sampleForm.trigger('sample')}
                  />
                </StackItem>
              </Stack>
            )}
          </ExpandableSection>
        </StackItem>
      )}
    </Stack>
  )
}
