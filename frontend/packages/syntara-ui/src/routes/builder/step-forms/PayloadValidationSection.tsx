import {
  FormGroup,
  FormHelperText,
  HelperText,
  HelperTextItem,
  Stack,
  StackItem,
  ToggleGroup,
  ToggleGroupItem,
} from '@patternfly/react-core'
import type { ReactNode } from 'react'
import { useCallback, useId, useState } from 'react'
import { Controller, useFormContext } from 'react-hook-form'

import { ExpandableCodeEditor } from '../components/ExpandableCodeEditor'
import { JsonEditorControls } from '../components/JsonEditorToolbar'

import { SimpleSchemaBuilder } from './SimpleSchemaBuilder'
import { fieldsToJsonSchema, jsonSchemaToFields, type SimpleField, type SimpleSchemaReason } from './simpleSchemaUtils'
import type { TriggerFormData } from './triggerFormSchema'

type ValidationMode = 'simple' | 'advanced'

const REASON_MESSAGES: Record<SimpleSchemaReason, string> = {
  ok: '',
  invalid_json: 'Invalid JSON syntax. Fix errors in advanced mode before switching to simple mode.',
  complex_schema:
    'This schema uses features not supported in simple mode (nested objects, combinators, etc.). Use advanced mode to edit it.',
}

function reasonToMessage(reason: SimpleSchemaReason): string {
  return REASON_MESSAGES[reason]
}

type PayloadValidationSectionProps = {
  /** Placeholder code shown when the field value is empty. */
  defaultCode: string
  /** Example code injected by the "Load example" toolbar action. */
  exampleCode: string
  /** Title of the full-screen modal editor. */
  modalTitle: string
  /** Accessible label for the code editor. */
  ariaLabel: string
  /** Filename used when downloading the schema. */
  downloadFilename: string
  /** Helper text shown below the editor when there is no error. */
  helperText: string
  /** Validation error message (if any). */
  error?: string
  /** Label element rendered above the mode toggle. */
  label?: ReactNode
}

function ModeToggle({
  activeMode,
  onChange,
  idPrefix,
}: Readonly<{ activeMode: ValidationMode; onChange: (mode: ValidationMode) => void; idPrefix: string }>) {
  const simpleId = `${idPrefix}-simple`
  const advancedId = `${idPrefix}-advanced`
  const isSimple = activeMode === 'simple'
  const isAdvanced = activeMode === 'advanced'
  const selectSimple = () => onChange('simple')
  const selectAdvanced = () => onChange('advanced')

  return (
    <ToggleGroup aria-label="Validation mode" isCompact>
      <ToggleGroupItem text="Simple" buttonId={simpleId} isSelected={isSimple} onChange={selectSimple} />
      <ToggleGroupItem text="Advanced" buttonId={advancedId} isSelected={isAdvanced} onChange={selectAdvanced} />
    </ToggleGroup>
  )
}

export function PayloadValidationSection({
  defaultCode,
  exampleCode,
  modalTitle,
  ariaLabel,
  downloadFilename,
  helperText,
  error,
  label,
}: Readonly<PayloadValidationSectionProps>) {
  const { control, getValues } = useFormContext<TriggerFormData>()
  const idPrefix = useId()
  const [mode, setMode] = useState<ValidationMode>(() => {
    const currentCode = getValues('inputSchema')
    if (currentCode?.trim()) {
      const parsed = jsonSchemaToFields(currentCode)
      if (!parsed.isSimpleSchema) return 'advanced'
    }
    return 'simple'
  })
  const [switchError, setSwitchError] = useState<string | null>(null)

  const handleModeChange = useCallback((newMode: ValidationMode, currentCode: string | undefined) => {
    if (newMode === 'simple') {
      const parsed = jsonSchemaToFields(currentCode)
      if (!parsed.isSimpleSchema) {
        setSwitchError(reasonToMessage(parsed.reason))
        return
      }
      setSwitchError(null)
    } else {
      setSwitchError(null)
    }
    setMode(newMode)
  }, [])

  return (
    <Controller
      control={control}
      name="inputSchema"
      render={({ field }) => (
        <PayloadValidationContent
          mode={mode}
          onModeChange={(newMode) => handleModeChange(newMode, field.value)}
          code={field.value ?? ''}
          onCodeChange={field.onChange}
          onBlur={field.onBlur}
          defaultCode={defaultCode}
          exampleCode={exampleCode}
          modalTitle={modalTitle}
          ariaLabel={ariaLabel}
          downloadFilename={downloadFilename}
          helperText={helperText}
          error={error}
          switchError={switchError}
          label={label}
          idPrefix={idPrefix}
        />
      )}
    />
  )
}

type PayloadValidationContentProps = {
  mode: ValidationMode
  onModeChange: (mode: ValidationMode) => void
  code: string
  onCodeChange: (code: string) => void
  onBlur: () => void
  defaultCode: string
  exampleCode: string
  modalTitle: string
  ariaLabel: string
  downloadFilename: string
  helperText: string
  error?: string
  switchError: string | null
  label?: ReactNode
  idPrefix: string
}

function SimpleSchemaMode({ code, onCodeChange }: Readonly<{ code: string; onCodeChange: (code: string) => void }>) {
  const [localFields, setLocalFields] = useState<SimpleField[]>(() => jsonSchemaToFields(code).fields)

  const handleFieldsChange = useCallback(
    (fields: SimpleField[]) => {
      setLocalFields(fields)
      onCodeChange(fieldsToJsonSchema(fields, true))
    },
    [onCodeChange]
  )

  return <SimpleSchemaBuilder fields={localFields} onFieldsChange={handleFieldsChange} />
}

function PayloadValidationContent({
  mode,
  onModeChange,
  code,
  onCodeChange,
  onBlur,
  defaultCode,
  exampleCode,
  modalTitle,
  ariaLabel,
  downloadFilename,
  helperText,
  error,
  switchError,
  label,
  idPrefix,
}: Readonly<PayloadValidationContentProps>) {
  const displayError = error ?? switchError
  return (
    <FormGroup label={label} fieldId="payload-validation">
      <Stack hasGutter>
        <StackItem>
          <ModeToggle activeMode={mode} onChange={onModeChange} idPrefix={idPrefix} />
        </StackItem>

        {mode === 'simple' ? (
          <StackItem>
            <SimpleSchemaMode code={code} onCodeChange={onCodeChange} />
          </StackItem>
        ) : (
          <>
            <StackItem>
              <ExpandableCodeEditor
                code={code}
                onCodeChange={onCodeChange}
                onBlur={onBlur}
                language="json"
                height="150px"
                modalTitle={modalTitle}
                ariaLabel={ariaLabel}
                additionalControls={
                  <JsonEditorControls
                    code={code}
                    onCodeChange={onCodeChange}
                    defaultCode={defaultCode}
                    downloadFilename={downloadFilename}
                    exampleCode={exampleCode}
                  />
                }
              />
            </StackItem>
            {helperText && !displayError && (
              <StackItem>
                <FormHelperText>
                  <HelperText>
                    <HelperTextItem>{helperText}</HelperTextItem>
                  </HelperText>
                </FormHelperText>
              </StackItem>
            )}
          </>
        )}

        {displayError && (
          <StackItem>
            <FormHelperText>
              <HelperText>
                <HelperTextItem variant="error">{displayError}</HelperTextItem>
              </HelperText>
            </FormHelperText>
          </StackItem>
        )}
      </Stack>
    </FormGroup>
  )
}
