import type { FieldPath, FieldValues } from 'react-hook-form'

import { SynFormField } from '../../components/forms/SynFormField'

import { TypeaheadSelect } from './TypeaheadSelect'

type PrincipalFieldProps<TFieldValues extends FieldValues> = {
  name: FieldPath<TFieldValues>
  label: string
  fieldId: string
  options: { value: string; label: string }[]
  placeholder: string
  onSearchChange?: (term: string) => void
  hasMore?: boolean
  isLoading?: boolean
}

export function PrincipalField<TFieldValues extends FieldValues>({
  name,
  label,
  fieldId,
  options,
  placeholder,
  onSearchChange,
  hasMore,
  isLoading,
}: Readonly<PrincipalFieldProps<TFieldValues>>) {
  return (
    <SynFormField<TFieldValues, FieldPath<TFieldValues>> name={name} label={label} fieldId={fieldId} isRequired>
      {({ field, fieldState }) => (
        <TypeaheadSelect
          id={fieldId}
          ariaLabel={label}
          options={options}
          selected={field.value ?? ''}
          onChange={field.onChange}
          placeholder={placeholder}
          hasError={!!fieldState.error}
          onSearchChange={onSearchChange}
          hasMore={hasMore}
          isLoading={isLoading}
        />
      )}
    </SynFormField>
  )
}
