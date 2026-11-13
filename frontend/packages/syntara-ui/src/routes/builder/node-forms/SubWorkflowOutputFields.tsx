import {
  Alert,
  FormGroup,
  FormHelperText,
  HelperText,
  HelperTextItem,
  Stack,
  StackItem,
  ToggleGroup,
  ToggleGroupItem,
} from '@patternfly/react-core'
import { useCallback, useEffect, useId, useMemo, useState } from 'react'
import { useFormContext, useWatch } from 'react-hook-form'

import { FormLabelWithHelp } from '../../../components/FormLabelWithHelp'
import { parseJsonSchema } from '../../../utils/jsonSafeParse'
import { ExpandableCodeEditor } from '../components/ExpandableCodeEditor'
import { JsonEditorControls } from '../components/JsonEditorToolbar'
import {
  outputFieldsFromSchema,
  outputMappingFromFields,
  outputSchemaFromFields,
} from '../utils/subWorkflowOutputContract'
import { useIsVersionView } from '../VersionViewContext'

import { SubWorkflowAdvancedMappings } from './SubWorkflowAdvancedMappings'
import { SubWorkflowSimpleOutputFields } from './SubWorkflowSimpleOutputFields'
import { DEFAULT_JSON_SCHEMA } from './triggerFormSchema'
import type { TriggerFormData } from './triggerFormSchema'

function withUpdatedOutputMapping(
  mapping: Record<string, string>,
  path: string,
  expression: string
): Record<string, string> {
  const nextMapping = { ...mapping }
  if (expression.trim()) nextMapping[path] = expression
  else delete nextMapping[path]
  return nextMapping
}

function getAdvancedOutputMapping(
  schema: ReturnType<typeof parseJsonSchema>,
  currentMapping: Record<string, string>
): Record<string, string> | undefined {
  const properties = schema?.properties
  if (typeof properties !== 'object' || properties === null || Array.isArray(properties)) return undefined
  return outputMappingFromFields(outputFieldsFromSchema(schema, currentMapping))
}

export function SubWorkflowOutputFields({
  triggerId,
  triggerIndex,
}: Readonly<{ triggerId: string; triggerIndex: number }>) {
  const isVersionView = useIsVersionView()
  const {
    control,
    setValue,
    formState: { errors },
  } = useFormContext<TriggerFormData>()

  const watchedOutputRows = useWatch({ control, name: 'outputFields' })
  const outputRows = useMemo(() => watchedOutputRows ?? [], [watchedOutputRows])
  const schemaText = useWatch({ control, name: 'outputSchema' }) ?? ''
  const watchedOutputMapping = useWatch({ control, name: 'outputMapping' })
  const outputMapping = useMemo(() => watchedOutputMapping ?? {}, [watchedOutputMapping])
  const parsedSchema = useMemo(() => parseJsonSchema(schemaText), [schemaText])
  const advancedFields = useMemo(
    () => outputFieldsFromSchema(parsedSchema, outputMapping),
    [parsedSchema, outputMapping]
  )
  const [editorMode, setEditorMode] = useState<'simple' | 'advanced'>('simple')
  const [modeError, setModeError] = useState('')
  const modeId = useId()

  const handleAdvancedMappingChange = useCallback(
    (path: string, expression: string) =>
      setValue('outputMapping', withUpdatedOutputMapping(outputMapping, path, expression)),
    [outputMapping, setValue]
  )

  // Sync Simple mode changes to output_schema and output_mapping
  useEffect(() => {
    if (editorMode === 'simple') {
      const schema = outputSchemaFromFields(outputRows, parsedSchema)
      const mapping = outputMappingFromFields(outputRows)
      const nextSchemaText = schema ? JSON.stringify(schema, null, 2) : ''
      if (nextSchemaText !== schemaText) setValue('outputSchema', nextSchemaText)
      if (JSON.stringify(mapping) !== JSON.stringify(outputMapping)) setValue('outputMapping', mapping)
    }
  }, [editorMode, outputRows, outputMapping, parsedSchema, schemaText, setValue])

  // Keep Advanced mode mappings aligned with the schema while preserving matching paths.
  useEffect(() => {
    if (editorMode !== 'advanced') return
    const nextMapping = getAdvancedOutputMapping(parsedSchema, outputMapping)
    if (!nextMapping) return
    if (JSON.stringify(nextMapping) !== JSON.stringify(outputMapping)) {
      setValue('outputMapping', nextMapping, { shouldDirty: true, shouldValidate: true })
    }
  }, [editorMode, outputMapping, parsedSchema, setValue])

  const selectSimpleMode = () => {
    if (editorMode === 'simple') return

    // Switching to Simple - validate JSON
    const schema = parseJsonSchema(schemaText)
    if (schemaText.trim() && !schema) {
      setModeError('Cannot switch to Simple mode: Invalid JSON schema. Fix errors in Advanced mode first.')
      return
    }
    setModeError('')
    setValue('outputFields', advancedFields)
    setEditorMode('simple')
  }

  const selectAdvancedMode = () => {
    if (editorMode === 'advanced') return

    // Switching to Advanced - build JSON from Simple mode rows
    const schema = outputSchemaFromFields(outputRows, parsedSchema)
    setValue('outputSchema', schema ? JSON.stringify(schema, null, 2) : '')
    setValue('outputMapping', outputMappingFromFields(outputRows))
    setModeError('')
    setEditorMode('advanced')
  }

  const simpleModeHelpText =
    'Name each field and choose the child step output that supplies it. The field type is inferred.'
  const advancedModeHelpText =
    'Edit the output JSON Schema directly, then map each declared field to a child step output.'

  return (
    <Stack hasGutter>
      <StackItem>
        <FormGroup
          label={
            <FormLabelWithHelp
              label="Output definition"
              helpText={editorMode === 'simple' ? simpleModeHelpText : advancedModeHelpText}
            />
          }
          fieldId="output-definition"
        >
          <Stack hasGutter>
            <StackItem>
              <ToggleGroup aria-label="Output definition mode" isCompact>
                <ToggleGroupItem
                  text="Simple"
                  buttonId={`${modeId}-simple`}
                  isSelected={editorMode === 'simple'}
                  onChange={selectSimpleMode}
                  isDisabled={isVersionView}
                />
                <ToggleGroupItem
                  text="Advanced"
                  buttonId={`${modeId}-advanced`}
                  isSelected={editorMode === 'advanced'}
                  onChange={selectAdvancedMode}
                  isDisabled={isVersionView}
                />
              </ToggleGroup>
            </StackItem>
            {modeError && (
              <StackItem>
                <Alert variant="danger" isInline title="Mode switch error">
                  {modeError}
                </Alert>
              </StackItem>
            )}
          </Stack>
        </FormGroup>
      </StackItem>

      {editorMode === 'simple' ? (
        <SubWorkflowSimpleOutputFields
          triggerId={triggerId}
          triggerIndex={triggerIndex}
          isVersionView={isVersionView}
        />
      ) : (
        <StackItem>
          <Stack hasGutter>
            <StackItem>
              <FormGroup
                label={
                  <FormLabelWithHelp
                    label="Output schema"
                    helpText="Define the output schema as JSON. The schema describes which fields parent workflows can access."
                  />
                }
                fieldId="output-schema"
              >
                <Stack>
                  <StackItem>
                    <ExpandableCodeEditor
                      code={schemaText}
                      onCodeChange={(code) => setValue('outputSchema', code)}
                      language="json"
                      height="150px"
                      modalTitle="Edit output schema"
                      ariaLabel="Output schema editor"
                      additionalControls={
                        <JsonEditorControls
                          code={schemaText}
                          onCodeChange={(code) => setValue('outputSchema', code)}
                          defaultCode={DEFAULT_JSON_SCHEMA}
                          downloadFilename="output-schema.json"
                          exampleCode={JSON.stringify(
                            {
                              type: 'object',
                              properties: {
                                artifact_url: { type: 'string', description: 'Build artifact URL' },
                                release_tag: { type: 'string', description: 'Release version tag' },
                              },
                              required: ['artifact_url'],
                            },
                            null,
                            2
                          )}
                        />
                      }
                    />
                  </StackItem>
                  {!errors.outputSchema?.message && (
                    <StackItem>
                      <FormHelperText>
                        <HelperText>
                          <HelperTextItem>
                            Define the public fields the parent workflow can use. Map each field to a child step output
                            below.
                          </HelperTextItem>
                        </HelperText>
                      </FormHelperText>
                    </StackItem>
                  )}
                  {errors.outputSchema?.message && (
                    <StackItem>
                      <FormHelperText>
                        <HelperText>
                          <HelperTextItem variant="error">{errors.outputSchema.message}</HelperTextItem>
                        </HelperText>
                      </FormHelperText>
                    </StackItem>
                  )}
                </Stack>
              </FormGroup>
            </StackItem>

            <StackItem>
              <SubWorkflowAdvancedMappings
                fields={advancedFields}
                outputMapping={outputMapping}
                triggerId={triggerId}
                triggerIndex={triggerIndex}
                isVersionView={isVersionView}
                onMappingChange={handleAdvancedMappingChange}
              />
            </StackItem>
          </Stack>
        </StackItem>
      )}
    </Stack>
  )
}
