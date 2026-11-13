import { Flex, FlexItem, TextInput } from '@patternfly/react-core'
import type { FormDefinition } from '@syntara/contracts'
import { useFormContext } from 'react-hook-form'

import { FormFieldTypeEnum } from '../../../forms'
import { SynFormField } from '../SynFormField'

import { formFieldBuilderLabelHelp } from './formFieldBuilderFieldHelp'

type FormFieldBuilderCardHeaderLabelProps = {
  index: number
  idPrefix: string
  fieldType: FormDefinition['fields'][number]['type']
  isDisabled?: boolean
  /** Called before the label updates in react-hook-form so the parent can sync generated value names. */
  onLabelChange: (nextLabel: string) => void
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
  const checkboxLabelHelp = formFieldBuilderLabelHelp('checkboxLabel', 'Checkbox label')

  const labelField = (
    <SynFormField
      control={control}
      name={`fields.${index}.label`}
      label={isCheckboxField ? 'Checkbox label' : 'Field label'}
      fieldId={`${idPrefix}-label`}
      isRequired={!isCheckboxField}
      hideFormGroupLabel={isCheckboxField}
      labelHelp={isCheckboxField ? undefined : formFieldBuilderLabelHelp('label', 'Field label')}
    >
      {({ field, fieldState }) => (
        <TextInput
          id={`${idPrefix}-label`}
          aria-label={isCheckboxField ? 'Checkbox label' : 'Field label'}
          value={field.value ?? ''}
          validated={fieldState.error ? 'error' : 'default'}
          isDisabled={isDisabled}
          onChange={(_event, value) => {
            onLabelChange(value)
            field.onChange(value)
          }}
          onBlur={field.onBlur}
        />
      )}
    </SynFormField>
  )

  if (!isCheckboxField) {
    return labelField
  }

  return (
    <Flex alignItems={{ default: 'alignItemsFlexStart' }} gap={{ default: 'gapSm' }}>
      <FlexItem grow={{ default: 'grow' }}>{labelField}</FlexItem>
      {checkboxLabelHelp ? <FlexItem>{checkboxLabelHelp}</FlexItem> : null}
    </Flex>
  )
}
