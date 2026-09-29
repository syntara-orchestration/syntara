import { Flex, FlexItem, FormGroup, TextInput } from '@patternfly/react-core'
import type { FormDefinition } from '@syntara/contracts'
import { Controller, useFormContext } from 'react-hook-form'

import { FormFieldTypeEnum } from '../../../forms'

import { formFieldBuilderLabelHelp } from './formFieldBuilderFieldHelp'

type FormFieldBuilderCardHeaderLabelProps = {
  index: number
  idPrefix: string
  fieldType: FormDefinition['fields'][number]['type']
  isDisabled?: boolean
  onLabelChange: (value: string) => void
}

export function FormFieldBuilderCardHeaderLabel({
  index,
  idPrefix,
  fieldType,
  isDisabled,
  onLabelChange,
}: Readonly<FormFieldBuilderCardHeaderLabelProps>) {
  const { control } = useFormContext<FormDefinition>()
  const isCheckboxField = fieldType === FormFieldTypeEnum.CHECKBOX

  return (
    <Controller
      control={control}
      name={`fields.${index}.label`}
      render={({ field: rhfField, fieldState }) => {
        const labelInput = (
          <TextInput
            id={`${idPrefix}-label`}
            aria-label={isCheckboxField ? 'Checkbox label' : 'Field label'}
            value={rhfField.value ?? ''}
            validated={fieldState.error ? 'error' : 'default'}
            isDisabled={isDisabled}
            onChange={(_event, value) => onLabelChange(value)}
            onBlur={rhfField.onBlur}
          />
        )

        if (isCheckboxField) {
          const labelHelp = formFieldBuilderLabelHelp('checkboxLabel', 'Checkbox label')
          return (
            <Flex alignItems={{ default: 'alignItemsFlexStart' }} gap={{ default: 'gapSm' }}>
              <FlexItem grow={{ default: 'grow' }}>{labelInput}</FlexItem>
              {labelHelp ? <FlexItem>{labelHelp}</FlexItem> : null}
            </Flex>
          )
        }

        return (
          <FormGroup
            label="Field label"
            fieldId={`${idPrefix}-label`}
            isRequired
            labelHelp={formFieldBuilderLabelHelp('label', 'Field label')}
          >
            {labelInput}
          </FormGroup>
        )
      }}
    />
  )
}
