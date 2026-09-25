import type { Control, FieldValues, Path } from 'react-hook-form'

import { SynTextField } from '../../../../components/forms/SynTextField'
import { useIsVersionView } from '../../VersionViewContext'

type ActivityNameFieldProps<T extends FieldValues & { name?: string }> = {
  fieldId: string
  placeholder?: string
  ariaLabel?: string
  /** When true, omits the FormGroup label (header compact input). */
  hideFormGroupLabel?: boolean
  /**
   * Pass when the field renders outside `SynForm` (e.g. builder header slot).
   * Omit inside the form tree so context is used.
   */
  control?: Control<T>
}

export function ActivityNameField<T extends FieldValues & { name?: string }>({
  fieldId,
  placeholder = 'Enter activity name',
  ariaLabel,
  hideFormGroupLabel = true,
  control,
}: ActivityNameFieldProps<T>) {
  const isVersionView = useIsVersionView()
  const label = ariaLabel ?? placeholder

  return (
    <div style={{ width: '18rem', maxWidth: '100%' }}>
      <SynTextField
        name={'name' as Path<T>}
        control={control}
        label={label}
        fieldId={fieldId}
        ariaLabel={label}
        hideFormGroupLabel={hideFormGroupLabel}
        placeholder={placeholder}
        isDisabled={isVersionView}
      />
    </div>
  )
}
