import { TextInput } from '@patternfly/react-core'
import type { Path, UseFormReturn } from 'react-hook-form'

import { useIsVersionView } from '../../VersionViewContext'

type ActivityNameFieldProps<T extends { name?: string }> = {
  register: UseFormReturn<T>['register']
  fieldId: string
  placeholder?: string
  ariaLabel?: string
}

export function ActivityNameField<T extends { name?: string }>({
  register,
  fieldId,
  placeholder = 'Enter activity name',
  ariaLabel,
}: ActivityNameFieldProps<T>) {
  const isVersionView = useIsVersionView()

  return (
    <TextInput
      {...register('name' as Path<T>)}
      id={fieldId}
      placeholder={placeholder}
      type="text"
      aria-label={ariaLabel ?? placeholder}
      isDisabled={isVersionView}
      style={{ width: '18rem', maxWidth: '100%' }}
    />
  )
}
