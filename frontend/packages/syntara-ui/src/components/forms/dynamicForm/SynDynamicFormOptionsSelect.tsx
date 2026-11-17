import type { ControllerRenderProps, FieldValues } from 'react-hook-form'

import type { DynamicOptionsResolver } from '../SynDynamicForm.types'

import { OptionsTypeaheadSelect } from './OptionsTypeaheadSelect'
import type { OptionsFormField } from './synDynamicFormFieldTypes'
import { useDynamicFormFieldOptions } from './useDynamicFormFieldOptions'

type SynDynamicFormOptionsSelectProps<T extends FieldValues> = {
  field: OptionsFormField
  rhfField: ControllerRenderProps<T>
  fieldId: string
  ariaLabel: string
  isMulti: boolean
  isDisabled?: boolean
  resolveDynamicOptions?: DynamicOptionsResolver
}

export function SynDynamicFormOptionsSelect<T extends FieldValues>({
  field,
  rhfField,
  fieldId,
  ariaLabel,
  isMulti,
  isDisabled,
  resolveDynamicOptions,
}: Readonly<SynDynamicFormOptionsSelectProps<T>>) {
  const { options, isLoading, loadErrorMessage } = useDynamicFormFieldOptions(field, resolveDynamicOptions)

  return (
    <OptionsTypeaheadSelect
      fieldId={fieldId}
      ariaLabel={ariaLabel}
      options={options}
      value={rhfField.value}
      onChange={rhfField.onChange}
      isMulti={isMulti}
      isDisabled={isDisabled}
      isLoading={isLoading}
      loadErrorMessage={loadErrorMessage}
    />
  )
}
