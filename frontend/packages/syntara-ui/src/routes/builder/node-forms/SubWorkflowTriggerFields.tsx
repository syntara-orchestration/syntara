import {
  Alert,
  Content,
  ContentVariants,
  FormGroup,
  FormHelperText,
  HelperText,
  HelperTextItem,
  Stack,
  StackItem,
  Title,
} from '@patternfly/react-core'
import { useFormContext, useFormState } from 'react-hook-form'

import { FormLabelWithHelp } from '../../../components/FormLabelWithHelp'
import { SynFormField } from '../../../components/forms/SynFormField'
import { ExpandableCodeEditor } from '../components/ExpandableCodeEditor'
import { JsonEditorControls } from '../components/JsonEditorToolbar'

import { SubWorkflowOutputFields } from './SubWorkflowOutputFields'
import { DEFAULT_JSON_SCHEMA, type TriggerFormData } from './triggerFormSchema'

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
  triggerId,
  triggerIndex,
}: Readonly<{
  triggerId: string
  triggerIndex: number
}>) {
  const { control } = useFormContext<TriggerFormData>()
  const { errors: formErrors } = useFormState({ control })
  const inputSchemaError = formErrors.inputSchema?.message

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
        <SynFormField name="inputSchema" label="" hideFormGroupLabel hideFooter control={control}>
          {({ field }) => (
            <FormGroup
              label={
                <FormLabelWithHelp
                  label="Input schema"
                  helpText="Define an input schema for the data a parent workflow must supply when it invokes this workflow as a sub-workflow. Click Insert example to populate the field with a template schema."
                />
              }
              fieldId="input-schema"
            >
              <Stack hasGutter>
                <StackItem>
                  <ExpandableCodeEditor
                    code={field.value ?? ''}
                    onCodeChange={field.onChange}
                    onBlur={field.onBlur}
                    language="json"
                    height="150px"
                    modalTitle="Edit input schema"
                    ariaLabel="Input schema editor"
                    additionalControls={
                      <JsonEditorControls
                        code={field.value ?? ''}
                        onCodeChange={field.onChange}
                        defaultCode={DEFAULT_JSON_SCHEMA}
                        downloadFilename="input-schema.json"
                        exampleCode={EXAMPLE_INPUT_SCHEMA}
                      />
                    }
                  />
                </StackItem>
                {!inputSchemaError && (
                  <StackItem>
                    <FormHelperText>
                      <HelperText>
                        <HelperTextItem>
                          Optional JSON Schema defining the input data required to run this workflow.
                        </HelperTextItem>
                      </HelperText>
                    </FormHelperText>
                  </StackItem>
                )}
                {inputSchemaError && (
                  <StackItem>
                    <FormHelperText>
                      <HelperText>
                        <HelperTextItem variant="error">{inputSchemaError}</HelperTextItem>
                      </HelperText>
                    </FormHelperText>
                  </StackItem>
                )}
              </Stack>
            </FormGroup>
          )}
        </SynFormField>
      </StackItem>

      <StackItem>
        <Stack hasGutter>
          <StackItem>
            <Stack>
              <StackItem>
                <Title headingLevel="h3">Returned outputs</Title>
              </StackItem>
              <StackItem>
                <Content component={ContentVariants.p}>
                  Define the values this workflow returns by mapping each public output field to a child step output.
                  The parent workflow can use only the fields declared here.
                </Content>
              </StackItem>
            </Stack>
          </StackItem>
          <StackItem>
            <SubWorkflowOutputFields triggerId={triggerId} triggerIndex={triggerIndex} />
          </StackItem>
        </Stack>
      </StackItem>
    </Stack>
  )
}
