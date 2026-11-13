import { Content, ExpandableSection, Stack, StackItem, TextArea } from '@patternfly/react-core'
import { useState } from 'react'
import { useForm, useFormContext, useWatch } from 'react-hook-form'
import { z } from 'zod'

import { FieldHelpPopover } from '../../../components/FieldHelpPopover'
import { SynFormField } from '../../../components/forms/SynFormField'

import { KafkaFilterTest } from './KafkaFilterTest'
import styles from './KafkaSubscribeFilter.module.css'
import { hasKafkaFilterExpression } from './kafkaSubscribeMapping'
import { zodResolver } from './shared/formSchemaUtils'
import type { TriggerFormData } from './triggerFormSchema'

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

const CEL_HELP = (
  <Stack hasGutter className={styles.help} role="region" aria-label="CEL guidance and examples" tabIndex={0}>
    <Content component="p">
      The only root variable is input. Combine conditions explicitly with &amp;&amp;, ||, ! and parentheses. Use ==, !=,
      &lt;, &lt;=, &gt;, &gt;= and in for comparisons. The result must be boolean. String methods include contains(),
      startsWith(), endsWith() and matches(). matches() uses RE2 regular expressions and searches for a match; use ^ and
      $ to match the whole string. Lookarounds and backreferences are not supported.
    </Content>
    <Content component="p">
      key and each header value have kind (text, binary or null), base64, and text when UTF-8 decoding succeeds. Header
      names are case-sensitive; duplicate values are lists in occurrence order. Use has() or in before accessing
      optional fields. has() tests presence, so a present null value still needs a null check. metadata includes topic,
      partition, string offset, timestamp_ms and timestamp_type. payload.state is decoded, not_decoded or decode_error;
      decoded JSON is in payload.value and may be null. cloudevents is currently null.
    </Content>
    <Content
      component="pre"
      className={styles.examples}
    >{`input.key.kind == "text" && input.key.text.startsWith("order-")
"region" in input.headers && input.headers["region"].exists(h, h.kind == "text" && h.text == "eu")
input.metadata.topic == "orders" && input.metadata.partition == 0
input.payload.state == "decoded" && input.payload.value != null && has(input.payload.value.status) && input.payload.value.status == "ready"
input.key.kind == "text" && input.key.text.matches("^order-[0-9]+$")`}</Content>
    <Content component="p">Each line above is a separate example. Compose your complete expression explicitly.</Content>
  </Stack>
)

export function KafkaSubscribeFilter({ isReadOnly }: Readonly<{ isReadOnly: boolean }>) {
  const { control, setValue, clearErrors } = useFormContext<TriggerFormData>()
  const expression = useWatch({ control, name: 'filterExpression' }) ?? ''
  const [isTesting, setTesting] = useState(false)
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
          labelHelp={<FieldHelpPopover headerContent="Filter expression (CEL)" helpText={CEL_HELP} />}
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
              validated={fieldState.error ? 'error' : 'default'}
              aria-invalid={Boolean(fieldState.error)}
              aria-describedby={describedBy}
              spellCheck={false}
            />
          )}
        </SynFormField>
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
                    hint="The sample is bound directly as input, without a wrapper or Kafka decoding. Edit this Kafka-shaped example to try different messages."
                  >
                    {({ field, fieldState, describedBy }) => (
                      <TextArea
                        id="kafka-filter-sample"
                        name={field.name}
                        value={field.value}
                        onChange={field.onChange}
                        onBlur={field.onBlur}
                        ref={field.ref}
                        rows={10}
                        spellCheck={false}
                        validated={fieldState.error ? 'error' : 'default'}
                        aria-invalid={Boolean(fieldState.error)}
                        aria-describedby={describedBy}
                      />
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
