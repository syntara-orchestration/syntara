import { FormGroup, TextInput } from '@patternfly/react-core'
import type { FormDefinition } from '@syntara/contracts'
import { Controller, useFormContext } from 'react-hook-form'

import { formFieldBuilderLabelHelp } from './formFieldBuilderFieldHelp'

type FormFieldBuilderCardHeaderLabelProps = {
  index: number
  idPrefix: string
  isDisabled?: boolean
  onLabelChange: (value: string) => void
}

export function FormFieldBuilderCardHeaderLabel({
  index,
  idPrefix,
  isDisabled,
  onLabelChange,
}: Readonly<FormFieldBuilderCardHeaderLabelProps>) {
  const { control } = useFormContext<FormDefinition>()

  return (
    <Controller
      control={control}
      name={`fields.${index}.label`}
      render={({ field: rhfField, fieldState }) => (
        <FormGroup
          label="Field label"
          fieldId={`${idPrefix}-label`}
          isRequired
          labelHelp={formFieldBuilderLabelHelp('label', 'Field label')}
        >
          <TextInput
            id={`${idPrefix}-label`}
            value={rhfField.value ?? ''}
            validated={fieldState.error ? 'error' : 'default'}
            isDisabled={isDisabled}
            onChange={(_event, value) => onLabelChange(value)}
            onBlur={rhfField.onBlur}
          />
        </FormGroup>
      )}
    />
  )
}
