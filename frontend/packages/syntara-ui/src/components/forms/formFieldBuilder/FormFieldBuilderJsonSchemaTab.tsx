import { Alert, Button, Content, ContentVariants, FormGroup, Stack, StackItem, TextArea } from '@patternfly/react-core'
import type { FormDefinition } from '@syntara/contracts'
import { useMemo, useState } from 'react'
import { useFormContext, useWatch } from 'react-hook-form'

import {
  formDefinitionToJsonSchemaString,
  jsonSchemaStringToFormDefinition,
  safeParseFormDefinition,
  type FormDefinitionSchemaInput,
} from '../../../forms'
import { SynConfirmationDialog } from '../../dialogs/SynConfirmationDialog'

import styles from './formFieldBuilder.module.css'
import { useFormFieldBuilderCommit } from './formFieldBuilderCommitContext'

export function FormFieldBuilderJsonSchemaTab() {
  const commit = useFormFieldBuilderCommit()
  const { control, setValue } = useFormContext<FormDefinition>()
  const fields = useWatch({ control, name: 'fields' })
  const [importText, setImportText] = useState('')
  const [importError, setImportError] = useState<string | null>(null)
  const [confirmReplaceOpen, setConfirmReplaceOpen] = useState(false)
  const [pendingImportFields, setPendingImportFields] = useState<FormDefinitionSchemaInput['fields'] | null>(null)

  const content = useMemo(() => {
    const parsed = safeParseFormDefinition({ fields })
    if (!parsed.success) {
      return { error: true as const, errors: parsed.errors }
    }
    return { error: false as const, json: formDefinitionToJsonSchemaString(parsed.data) }
  }, [fields])

  const applyImportedFields = (importedFields: FormDefinitionSchemaInput['fields']) => {
    setImportError(null)
    setValue('fields', importedFields, { shouldValidate: true })
    commit()
  }

  const handleLoadSchema = () => {
    const result = jsonSchemaStringToFormDefinition(importText)
    if (!result.success) {
      setImportError(result.error)
      return
    }
    const importedFields = result.data.fields as FormDefinitionSchemaInput['fields']
    if ((fields?.length ?? 0) > 0) {
      setPendingImportFields(importedFields)
      setConfirmReplaceOpen(true)
      return
    }
    applyImportedFields(importedFields)
  }

  const handleConfirmReplace = () => {
    if (pendingImportFields) {
      applyImportedFields(pendingImportFields)
    }
    setPendingImportFields(null)
    setConfirmReplaceOpen(false)
  }

  return (
    <Stack hasGutter>
      <StackItem>
        <Content component={ContentVariants.small}>
          Import supports schemas exported from this builder. Arbitrary JSON Schema may lose field types, defaults, or
          dynamic options.
        </Content>
      </StackItem>
      <StackItem>
        <FormGroup label="Import JSON Schema" fieldId="form-builder-json-import">
          <TextArea
            id="form-builder-json-import"
            value={importText}
            onChange={(_event, value) => {
              setImportText(value)
              if (importError) {
                setImportError(null)
              }
            }}
            placeholder="Paste JSON Schema to load fields into the builder"
            aria-label="Import JSON Schema"
            resizeOrientation="vertical"
            rows={8}
          />
        </FormGroup>
        {importError && (
          <Alert variant="danger" title={importError} isInline className={styles.jsonSchemaImportError} />
        )}
        <Button variant="secondary" onClick={handleLoadSchema} isDisabled={importText.trim() === ''}>
          Load into builder
        </Button>
      </StackItem>
      <StackItem>
        {content.error ? (
          <Stack hasGutter>
            <StackItem>
              <Alert variant="warning" title="Fix validation errors to generate JSON Schema" isInline />
            </StackItem>
            {content.errors.map((error) => (
              <StackItem key={`${error.field}-${error.message}`}>
                <Alert variant="warning" title={error.message} isInline />
              </StackItem>
            ))}
          </Stack>
        ) : (
          <pre aria-label="Generated JSON Schema">
            <code>{content.json}</code>
          </pre>
        )}
      </StackItem>
      <SynConfirmationDialog
        isOpen={confirmReplaceOpen}
        onClose={() => {
          setConfirmReplaceOpen(false)
          setPendingImportFields(null)
        }}
        onConfirm={handleConfirmReplace}
        title="Replace form fields?"
        confirmLabel="Replace fields"
        confirmVariant="danger"
        titleIconVariant="warning"
      >
        <Content component={ContentVariants.p}>
          Loading JSON Schema will replace all fields in the builder. This cannot be undone.
        </Content>
      </SynConfirmationDialog>
    </Stack>
  )
}
