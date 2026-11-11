import { Alert, Content, ContentVariants, Stack, StackItem } from '@patternfly/react-core'

import { FormLabelWithHelp } from '../../../components/FormLabelWithHelp'

import { PayloadValidationSection } from './PayloadValidationSection'
import { DEFAULT_JSON_SCHEMA } from './triggerFormSchema'

const EXAMPLE_INPUT_SCHEMA = JSON.stringify(
  {
    $schema: 'http://json-schema.org/draft-07/schema#',
    type: 'object',
    properties: {
      greeting: { type: 'string' },
    },
    required: ['greeting'],
  },
  null,
  2
)

/**
 * Configuration fields for the Sub-workflow (child) trigger.
 *
 * Mirrors the manual trigger's input-schema editor and adds an informational
 * callout explaining that this trigger makes the workflow invocable as a
 * sub-workflow once published.
 */
export function SubWorkflowTriggerFields({
  errors,
}: Readonly<{ errors: Readonly<{ inputSchema?: { message?: string } }> }>) {
  return (
    <Stack hasGutter>
      <StackItem>
        <Alert variant="info" isInline title="Workflow trigger" component="h4">
          <Content component={ContentVariants.p}>
            Once published, this workflow can be called from another workflow by configuring a sub-workflow node.
          </Content>
        </Alert>
      </StackItem>
      <StackItem>
        <PayloadValidationSection
          label={
            <FormLabelWithHelp
              label="Input schema"
              helpText="Define an input schema for the data a parent workflow must supply when it invokes this workflow as a sub-workflow. Click Insert example to populate the field with a template schema."
            />
          }
          defaultCode={DEFAULT_JSON_SCHEMA}
          exampleCode={EXAMPLE_INPUT_SCHEMA}
          modalTitle="Edit input schema"
          ariaLabel="Input schema editor"
          downloadFilename="input-schema.json"
          helperText="Optional JSON Schema defining the input data required to run this workflow."
          error={errors.inputSchema?.message}
        />
      </StackItem>
    </Stack>
  )
}
