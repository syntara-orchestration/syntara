import { StackItem } from '@patternfly/react-core'
import type { ReactElement } from 'react'
import type { FieldPath, FieldValues, PathValue } from 'react-hook-form'
import { useFormContext } from 'react-hook-form'

import { SynFormField } from '../../../components/forms/SynFormField'

import { AAPTypeaheadSelect } from './AAPTypeaheadSelect'

type AAPResourceItem = {
  readonly id: number
  readonly name: string
}

type AAPResourceSelectFieldProps<TFieldValues extends FieldValues> = {
  readonly label: string
  readonly fieldId: string
  readonly nameField: FieldPath<TFieldValues>
  readonly idField: FieldPath<TFieldValues>
  readonly items: readonly AAPResourceItem[]
  readonly isLoading: boolean
  readonly helperText: string
  readonly placeholderText: string
  readonly onSearchChange: (search: string) => void
  readonly labelHelp?: ReactElement
}

export function AAPResourceSelectField<TFieldValues extends FieldValues>({
  label,
  fieldId,
  nameField,
  idField,
  items,
  isLoading,
  helperText,
  placeholderText,
  onSearchChange,
  labelHelp,
}: AAPResourceSelectFieldProps<TFieldValues>) {
  const { setValue } = useFormContext<TFieldValues>()
  const options = items.map((item) => ({ value: String(item.id), label: item.name }))

  return (
    <StackItem>
      <SynFormField<TFieldValues, FieldPath<TFieldValues>>
        name={nameField}
        label={label}
        labelHelp={labelHelp}
        fieldId={fieldId}
        hint={helperText}
      >
        {({ field }) => {
          const selectedItem = items.find((item) => item.name === field.value)
          const selectedId = selectedItem ? String(selectedItem.id) : ''

          return (
            <AAPTypeaheadSelect
              id={fieldId}
              ariaLabel={label}
              options={options}
              selected={selectedId}
              onChange={(value) => {
                const matchedItem = items.find((item) => String(item.id) === value)
                if (matchedItem) {
                  field.onChange(matchedItem.name)
                  setValue(idField, matchedItem.id as PathValue<TFieldValues, typeof idField>)
                } else {
                  field.onChange('')
                  setValue(idField, undefined as PathValue<TFieldValues, typeof idField>)
                }
              }}
              onSearchChange={onSearchChange}
              placeholder={placeholderText}
              isLoading={isLoading}
            />
          )
        }}
      </SynFormField>
    </StackItem>
  )
}
