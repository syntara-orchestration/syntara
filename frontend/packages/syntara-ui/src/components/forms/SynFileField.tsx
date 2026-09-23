import { FileUpload } from '@patternfly/react-core'
import type { DropEvent, FileUploadProps } from '@patternfly/react-core'
import type { ReactElement } from 'react'
import { useEffect, useRef } from 'react'
import type { Control, ControllerFieldState, ControllerRenderProps, FieldPath, FieldValues } from 'react-hook-form'

import { SynFormField } from './SynFormField'

function getSelectedFile(value: unknown): File | null {
  return value instanceof File ? value : null
}

type SynFileFieldControlProps<TFieldValues extends FieldValues, TName extends FieldPath<TFieldValues>> = {
  field: ControllerRenderProps<TFieldValues, TName>
  fieldState: ControllerFieldState
  resolvedFieldId: string
  filenamePlaceholder: string
  browseButtonText: string
  dropzoneProps?: FileUploadProps['dropzoneProps']
  hideDefaultPreview: boolean
  isDisabled?: boolean
}

function SynFileFieldControl<TFieldValues extends FieldValues, TName extends FieldPath<TFieldValues>>({
  field,
  fieldState,
  resolvedFieldId,
  filenamePlaceholder,
  browseButtonText,
  dropzoneProps,
  hideDefaultPreview,
  isDisabled,
}: Readonly<SynFileFieldControlProps<TFieldValues, TName>>) {
  const wrapperRef = useRef<HTMLDivElement>(null)
  const selectedFile = getSelectedFile(field.value)

  useEffect(() => {
    const wrapper = wrapperRef.current
    if (!wrapper) return

    const handleFocusOut = (event: FocusEvent) => {
      if (!wrapper.contains(event.relatedTarget as Node | null)) {
        field.onBlur()
      }
    }

    wrapper.addEventListener('focusout', handleFocusOut)
    return () => wrapper.removeEventListener('focusout', handleFocusOut)
  }, [field])

  const handleFileInputChange = (_event: DropEvent, inputFile: File) => {
    field.onChange(inputFile)
  }

  const handleClearClick = () => {
    field.onChange(undefined)
  }

  return (
    // PF FileUpload does not expose onBlur; delegate blur to RHF when focus leaves the control.
    <div ref={wrapperRef}>
      <FileUpload
        id={resolvedFieldId}
        value={selectedFile ?? undefined}
        filename={selectedFile?.name ?? ''}
        filenamePlaceholder={filenamePlaceholder}
        onFileInputChange={handleFileInputChange}
        onClearClick={handleClearClick}
        browseButtonText={browseButtonText}
        dropzoneProps={dropzoneProps}
        hideDefaultPreview={hideDefaultPreview}
        validated={fieldState.error ? 'error' : 'default'}
        isDisabled={isDisabled}
      />
    </div>
  )
}

export type SynFileFieldProps<
  TFieldValues extends FieldValues = FieldValues,
  TName extends FieldPath<TFieldValues> = FieldPath<TFieldValues>,
> = {
  /** RHF field name — must match a key in the form schema. */
  name: TName
  /**
   * RHF `control` object from `useForm` or `useSynForm`. When omitted the
   * field reads from the nearest `FormProvider` context.
   */
  control?: Control<TFieldValues>
  /** Label text rendered above the file upload control. */
  label: string
  /**
   * HTML `id` used as `FormGroup.fieldId` and on the file upload control.
   * Defaults to the `name` prop.
   */
  fieldId?: string
  /** Marks the field as required with a visual indicator. */
  isRequired?: boolean
  /**
   * Popover content shown next to the label via PatternFly `FormGroup.labelHelp`.
   * Must be a `ReactElement` — PF6 does not accept plain nodes.
   */
  labelHelp?: ReactElement
  /**
   * Static helper text shown below the field when there is no validation error.
   * Replaced by the error message when a validation error is present.
   */
  hint?: string
  /** Placeholder shown when no file is selected. */
  filenamePlaceholder?: string
  /** Text for the browse/upload button. Defaults to "Upload". */
  browseButtonText?: string
  /** react-dropzone props forwarded to PatternFly `FileUpload`. */
  dropzoneProps?: FileUploadProps['dropzoneProps']
  /** Hides the default file preview area. */
  hideDefaultPreview?: boolean
  /** Disables the file upload control. */
  isDisabled?: boolean
}

/**
 * A file upload control bound to a react-hook-form `File | undefined` field.
 *
 * Combines `SynFormField` + PatternFly `FileUpload` with RHF bindings
 * pre-wired. Intended for single-file forms such as workflow import dialogs.
 *
 * @example
 * ```tsx
 * <SynFileField
 *   name="file"
 *   control={control}
 *   label="Workflow file"
 *   isRequired
 *   dropzoneProps={{ accept: { 'application/json': ['.json'] } }}
 * />
 * ```
 */
export function SynFileField<
  TFieldValues extends FieldValues = FieldValues,
  TName extends FieldPath<TFieldValues> = FieldPath<TFieldValues>,
>({
  name,
  control,
  label,
  fieldId,
  isRequired,
  labelHelp,
  hint,
  filenamePlaceholder = 'Drag and drop a file or upload one',
  browseButtonText = 'Upload',
  dropzoneProps,
  hideDefaultPreview = true,
  isDisabled,
}: Readonly<SynFileFieldProps<TFieldValues, TName>>) {
  const resolvedFieldId = fieldId ?? name

  return (
    <SynFormField
      name={name}
      control={control}
      label={label}
      fieldId={resolvedFieldId}
      isRequired={isRequired}
      labelHelp={labelHelp}
      hint={hint}
    >
      {({ field, fieldState }) => (
        <SynFileFieldControl<TFieldValues, TName>
          field={field}
          fieldState={fieldState}
          resolvedFieldId={resolvedFieldId}
          filenamePlaceholder={filenamePlaceholder}
          browseButtonText={browseButtonText}
          dropzoneProps={dropzoneProps}
          hideDefaultPreview={hideDefaultPreview}
          isDisabled={isDisabled}
        />
      )}
    </SynFormField>
  )
}
