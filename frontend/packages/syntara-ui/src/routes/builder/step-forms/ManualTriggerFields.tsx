import { StackItem } from '@patternfly/react-core'

import { FormLabelWithHelp } from '../../../components/FormLabelWithHelp'

import { PayloadValidationSection } from './PayloadValidationSection'
import { DEFAULT_JSON_SCHEMA } from './triggerFormSchema'

const EXAMPLE_INPUT_SCHEMA = JSON.stringify(
  {
    type: 'object',
    properties: {
      name: { type: 'string' },
    },
    required: ['name'],
  },
  null,
  2
)

export function ManualTriggerFields({
  errors,
}: Readonly<{ errors: Readonly<{ inputSchema?: { message?: string } }> }>) {
  return (
    <StackItem>
      <PayloadValidationSection
        label={
          <FormLabelWithHelp
            label="Input schema"
            helpText="Define an input schema to allow users to input data when running the workflow manually. Use this to simulate or test workflow runs with specific parameters. Click Insert example to populate the field with a template schema."
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
  )
}
