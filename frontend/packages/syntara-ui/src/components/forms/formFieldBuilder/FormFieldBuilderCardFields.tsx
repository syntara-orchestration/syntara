import { Checkbox, FormGroup, Stack, StackItem } from '@patternfly/react-core'
import type { FormDefinition, FormField } from '@syntara/contracts'
import { Controller, useFormContext } from 'react-hook-form'

import { FormFieldTypeEnum, type FormFieldType } from '../../../forms'
import { SynTextAreaField } from '../SynTextAreaField'
import { SynTextField } from '../SynTextField'

import { useFormFieldBuilderCommit } from './formFieldBuilderCommitContext'
import { getFormFieldBuilderExamplePlaceholders } from './formFieldBuilderExamplePlaceholders'
import { FormFieldBuilderFieldDefaultEditor } from './FormFieldBuilderFieldDefaultEditor'
import { formFieldBuilderLabelHelp } from './formFieldBuilderFieldHelp'
import { FormFieldBuilderFieldTypeSelect } from './FormFieldBuilderFieldTypeSelect'
import { FormFieldBuilderOptionsSection } from './FormFieldBuilderOptionsSection'

type FormFieldBuilderCardFieldsProps = {
  index: number
  field: FormField
  idPrefix: string
  isDisabled?: boolean
  valueNameLooksGenerated: boolean
  onTypeChange: (type: FormFieldType) => void
}

function isOptionsField(field: FormField): field is Extract<FormField, { type: 'dropdown' | 'multi_select' }> {
  return field.type === FormFieldTypeEnum.DROPDOWN || field.type === FormFieldTypeEnum.MULTI_SELECT
}

export function FormFieldBuilderCardFields({
  index,
  field,
  idPrefix,
  isDisabled,
  valueNameLooksGenerated,
  onTypeChange,
}: Readonly<FormFieldBuilderCardFieldsProps>) {
  const commit = useFormFieldBuilderCommit()
  const { control } = useFormContext<FormDefinition>()
  const examples = getFormFieldBuilderExamplePlaceholders(field.type)

  return (
    <Stack hasGutter>
      <StackItem>
        <FormGroup label="Field type" fieldId={`${idPrefix}-type`} isRequired>
          <FormFieldBuilderFieldTypeSelect
            fieldId={`${idPrefix}-type`}
            value={field.type}
            isDisabled={isDisabled}
            onChange={onTypeChange}
          />
        </FormGroup>
      </StackItem>
      <StackItem>
        <SynTextField
          name={`fields.${index}.value_name`}
          control={control}
          label="Value name"
          fieldId={`${idPrefix}-value-name`}
          isRequired
          isDisabled={isDisabled}
          labelHelp={formFieldBuilderLabelHelp('valueName', 'Value name')}
          hint={valueNameLooksGenerated ? 'Generated from the label above' : undefined}
          onValueChange={commit}
        />
      </StackItem>
      <StackItem>
        <Controller
          control={control}
          name={`fields.${index}.required`}
          render={({ field: rhfField }) => (
            <Checkbox
              id={`${idPrefix}-required`}
              label="Required"
              isChecked={Boolean(rhfField.value)}
              isDisabled={isDisabled}
              onChange={(_event, checked) => {
                rhfField.onChange(checked)
                commit()
              }}
            />
          )}
        />
      </StackItem>
      {field.type !== FormFieldTypeEnum.CHECKBOX && (
        <StackItem>
          <SynTextField
            name={`fields.${index}.placeholder`}
            control={control}
            label="Placeholder"
            fieldId={`${idPrefix}-placeholder`}
            isDisabled={isDisabled}
            placeholder={examples.placeholder}
            labelHelp={formFieldBuilderLabelHelp('placeholder', 'Placeholder')}
            onValueChange={commit}
          />
        </StackItem>
      )}
      <StackItem>
        {field.type === FormFieldTypeEnum.CHECKBOX || field.type === FormFieldTypeEnum.DATE ? (
          <SynTextAreaField
            name={`fields.${index}.help_text`}
            control={control}
            label="Help text"
            fieldId={`${idPrefix}-help`}
            isDisabled={isDisabled}
            placeholder={examples.helpText}
            labelHelp={formFieldBuilderLabelHelp('helpText', 'Help text')}
            rows={3}
            onValueChange={commit}
          />
        ) : (
          <SynTextField
            name={`fields.${index}.help_text`}
            control={control}
            label="Help text"
            fieldId={`${idPrefix}-help`}
            isDisabled={isDisabled}
            placeholder={examples.helpText}
            labelHelp={formFieldBuilderLabelHelp('helpText', 'Help text')}
            onValueChange={commit}
          />
        )}
      </StackItem>

      {isOptionsField(field) && (
        <StackItem>
          <FormFieldBuilderOptionsSection index={index} field={field} isDisabled={isDisabled} idPrefix={idPrefix} />
        </StackItem>
      )}

      <StackItem>
        <FormFieldBuilderFieldDefaultEditor index={index} field={field} isDisabled={isDisabled} idPrefix={idPrefix} />
      </StackItem>
    </Stack>
  )
}
