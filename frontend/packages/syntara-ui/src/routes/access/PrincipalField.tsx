import { FormGroup, FormHelperText, HelperText, HelperTextItem } from '@patternfly/react-core'
import { Controller, useForm } from 'react-hook-form'

import type { AssignRoleFormData } from './assignRoleSchema'
import { TypeaheadSelect } from './TypeaheadSelect'

type PrincipalFieldProps = {
  control: ReturnType<typeof useForm<AssignRoleFormData>>['control']
  name: 'userId' | 'groupId' | 'serviceAccountId'
  label: string
  fieldId: string
  options: { value: string; label: string }[]
  placeholder: string
  onSearchChange?: (term: string) => void
  hasMore?: boolean
  isLoading?: boolean
}

export function PrincipalField({
  control,
  name,
  label,
  fieldId,
  options,
  placeholder,
  onSearchChange,
  hasMore,
  isLoading,
}: Readonly<PrincipalFieldProps>) {
  return (
    <FormGroup label={label} isRequired fieldId={fieldId}>
      <Controller
        name={name}
        control={control}
        render={({ field, fieldState }) => (
          <>
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
            {fieldState.error && (
              <FormHelperText>
                <HelperText>
                  <HelperTextItem variant="error">{fieldState.error.message}</HelperTextItem>
                </HelperText>
              </FormHelperText>
            )}
          </>
        )}
      />
    </FormGroup>
  )
}
