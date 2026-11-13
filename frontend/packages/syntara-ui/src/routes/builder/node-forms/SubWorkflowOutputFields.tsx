import {
  Alert,
  Button,
  Card,
  CardBody,
  Checkbox,
  Content,
  ContentVariants,
  ExpandableSection,
  Flex,
  FlexItem,
  FormGroup,
  FormHelperText,
  HelperText,
  HelperTextItem,
  Stack,
  StackItem,
  TextInput,
  Title,
  ToggleGroup,
  ToggleGroupItem,
} from '@patternfly/react-core'
import { ExclamationTriangleIcon, RhUiAddIcon, RhUiTrashIcon } from '@patternfly/react-icons'
import { useCallback, useEffect, useId, useMemo, useRef, useState } from 'react'
import { Controller, useFieldArray, useFormContext, useWatch } from 'react-hook-form'

import { FormLabelWithHelp } from '../../../components/FormLabelWithHelp'
import { useWorkflowStore } from '../../../stores/useWorkflowStore'
import { parseJsonSchema } from '../../../utils/jsonSafeParse'
import { TypeaheadSelect } from '../../access/TypeaheadSelect'
import { extractStepIdFromExpression, isStepConditional } from '../utils/conditionalStepDetection'
import {
  outputFieldsFromSchema,
  outputMappingFromFields,
  outputSchemaFromFields,
} from '../utils/subWorkflowOutputContract'
import { useIsVersionView } from '../VersionViewContext'
import { ExpandableCodeEditor } from '../components/ExpandableCodeEditor'
import { JsonEditorControls } from '../components/JsonEditorToolbar'

import { DEFAULT_JSON_SCHEMA } from './triggerFormSchema'
import type { TriggerFormData } from './triggerFormSchema'

type Activity = {
  id: string
  name?: string | null
  type: string
  output_schema?: unknown
}

type OutputSourceOption = {
  value: string
  label: string
  stepName: string
  fieldName: string
  type: string
  description?: string
}

function getStepOutputChoices(
  activities: Activity[],
  edges: Array<{ source: string; target: string }>,
  triggerId: string,
  triggerIndex: number
): OutputSourceOption[] {
  // Find all steps reachable from this trigger
  const reachable = new Set([triggerId, `trigger-${triggerIndex}`])
  let previousSize = -1
  while (reachable.size !== previousSize) {
    previousSize = reachable.size
    for (const edge of edges) {
      if (reachable.has(edge.source)) reachable.add(edge.target)
    }
  }

  const choices: OutputSourceOption[] = []
  for (const activity of activities) {
    if (!reachable.has(activity.id)) continue

    // For now, we don't have step output schemas available at design time
    // Authors will need to manually enter the field path (e.g., ${step.field})
    // This is a V1 limitation - V2 can add step schema introspection
    choices.push({
      value: `\${${activity.id}}`,
      label: activity.name || activity.id,
      stepName: activity.name || activity.id,
      fieldName: '',
      type: 'unknown',
      description: `Reference output from ${activity.name || activity.id}`,
    })
  }

  return choices
}

function getFieldPathId(index: number, suffix: string) {
  return `subworkflow-output-${index}-${suffix}`
}

export function SubWorkflowOutputFields({
  triggerId,
  triggerIndex,
}: Readonly<{ triggerId: string; triggerIndex: number }>) {
  const isVersionView = useIsVersionView()
  const activities = useWorkflowStore((state) => state.currentWorkflow?.workflow.activities ?? [])
  const edges = useWorkflowStore((state) => state.edges)
  const {
    control,
    setValue,
    register,
    formState: { errors },
  } = useFormContext<TriggerFormData>()

  const { fields: outputRowKeys, append, remove, replace } = useFieldArray({ control, name: 'outputFields' })
  const outputRows = useWatch({ control, name: 'outputFields' }) ?? []
  const schemaText = useWatch({ control, name: 'outputSchema' }) ?? ''
  const parsedSchema = useMemo(() => parseJsonSchema(schemaText), [schemaText])
  const [editorMode, setEditorMode] = useState<'simple' | 'advanced'>('simple')
  const [modeError, setModeError] = useState('')
  const [expandedRows, setExpandedRows] = useState<Set<string>>(() => new Set())
  const lastVisualSchemaText = useRef(schemaText)
  const modeId = useId()

  const hasValidOutputSchema = Boolean(
    parsedSchema?.type === 'object' && typeof parsedSchema.properties === 'object' && parsedSchema.properties !== null
  )

  const sourceOptions = useMemo(
    () => getStepOutputChoices(activities, edges, triggerId, triggerIndex),
    [activities, edges, triggerId, triggerIndex]
  )

  // Check if a field's source step is conditional (may not always execute)
  const isFieldSourceConditional = useCallback(
    (expression: string): boolean => {
      const stepId = extractStepIdFromExpression(expression)
      if (!stepId) return false
      return isStepConditional(stepId, activities, edges, [triggerId, `trigger-${triggerIndex}`])
    },
    [activities, edges, triggerId, triggerIndex]
  )

  // Sync from Advanced mode schema changes to Simple mode
  useEffect(() => {
    if (editorMode === 'advanced' && schemaText !== lastVisualSchemaText.current) {
      const schema = parseJsonSchema(schemaText)
      if (schema) {
        const mapping = outputRows.reduce(
          (acc, row) => {
            if (row.path && row.expression) acc[row.path] = row.expression
            return acc
          },
          {} as Record<string, string>
        )
        const fields = outputFieldsFromSchema(schema, mapping)
        replace(fields)
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [schemaText, editorMode])

  // Sync Simple mode changes to output_schema and output_mapping
  useEffect(() => {
    if (editorMode === 'simple') {
      const schema = outputSchemaFromFields(outputRows, parsedSchema)
      const mapping = outputMappingFromFields(outputRows)
      setValue('outputSchema', schema ? JSON.stringify(schema, null, 2) : '')
      setValue('outputMapping', mapping)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [outputRows, editorMode])

  const selectSimpleMode = () => {
    if (editorMode === 'simple') return

    // Switching to Simple - validate JSON
    const schema = parseJsonSchema(schemaText)
    if (schemaText.trim() && !schema) {
      setModeError('Cannot switch to Simple mode: Invalid JSON schema. Fix errors in Advanced mode first.')
      return
    }
    setModeError('')
    setEditorMode('simple')
  }

  const selectAdvancedMode = () => {
    if (editorMode === 'advanced') return

    // Switching to Advanced - build JSON from Simple mode rows
    const schema = outputSchemaFromFields(outputRows, parsedSchema)
    const mapping = outputMappingFromFields(outputRows)
    setValue('outputSchema', schema ? JSON.stringify(schema, null, 2) : '')
    setValue('outputMapping', mapping)
    setModeError('')
    setEditorMode('advanced')
  }

  const handleAddField = () => {
    append({
      path: '',
      type: 'string',
      required: false,
      description: '',
      expression: '',
    })
  }

  const handleRemoveField = (index: number) => {
    remove(index)
  }

  const toggleRowExpanded = (index: number) => {
    const key = String(index)
    setExpandedRows((prev) => {
      const next = new Set(prev)
      if (next.has(key)) {
        next.delete(key)
      } else {
        next.add(key)
      }
      return next
    })
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
        <>
          {outputRowKeys.length === 0 && (
            <StackItem>
              <Alert variant="info" isInline isPlain title="No outputs configured">
                Add one to expose a child step value to the parent.
              </Alert>
            </StackItem>
          )}

          {outputRowKeys.map((rowKey, index) => {
            const row = outputRows[index]
            if (!row) return null

            return (
              <StackItem key={rowKey.id}>
                <Card isCompact>
                  <CardBody>
                    <Stack hasGutter>
                      <StackItem>
                        <Flex>
                          <FlexItem flex={{ default: 'flex_1' }}>
                            <FormGroup label="Field name" isRequired fieldId={getFieldPathId(index, 'path')}>
                              <TextInput
                                id={getFieldPathId(index, 'path')}
                                {...register(`outputFields.${index}.path` as const)}
                                placeholder="e.g., artifact_url or result.status"
                                isDisabled={isVersionView}
                              />
                              <FormHelperText>
                                <HelperText>
                                  <HelperTextItem>
                                    Use dot notation for nested fields (e.g., &quot;result.status&quot;)
                                  </HelperTextItem>
                                </HelperText>
                              </FormHelperText>
                            </FormGroup>
                          </FlexItem>
                          <FlexItem alignSelf={{ default: 'alignSelfCenter' }}>
                            <Button
                              variant="plain"
                              icon={<RhUiTrashIcon />}
                              onClick={() => handleRemoveField(index)}
                              aria-label="Remove field"
                              isDisabled={isVersionView}
                            />
                          </FlexItem>
                        </Flex>
                      </StackItem>

                      <StackItem>
                        <FormGroup label="Source expression" isRequired fieldId={getFieldPathId(index, 'expression')}>
                          <Controller
                            name={`outputFields.${index}.expression` as const}
                            control={control}
                            render={({ field }) => {
                              const isConditional = field.value && isFieldSourceConditional(field.value)
                              const isFieldRequired = outputRows[index]?.required

                              return (
                                <>
                                  <TypeaheadSelect
                                    id={getFieldPathId(index, 'expression')}
                                    ariaLabel="Source expression"
                                    options={sourceOptions.map((opt) => ({ value: opt.value, label: opt.label }))}
                                    selected={field.value ?? ''}
                                    onChange={(value) => field.onChange(value ?? '')}
                                    placeholder="Select step or enter template expression"
                                    isDisabled={isVersionView}
                                  />
                                  <FormHelperText>
                                    <HelperText>
                                      <HelperTextItem>
                                        Template expression (e.g., $&#123;deploy.artifact_url&#125;)
                                      </HelperTextItem>
                                      {isConditional && isFieldRequired && (
                                        <HelperTextItem variant="warning" icon={<ExclamationTriangleIcon />}>
                                          Step may not always execute. Consider making this field optional or ensure the
                                          step always runs.
                                        </HelperTextItem>
                                      )}
                                      {isConditional && !isFieldRequired && (
                                        <HelperTextItem variant="indeterminate" icon={<ExclamationTriangleIcon />}>
                                          Step may not execute in some workflow paths
                                        </HelperTextItem>
                                      )}
                                    </HelperText>
                                  </FormHelperText>
                                </>
                              )
                            }}
                          />
                        </FormGroup>
                      </StackItem>

                      <StackItem>
                        <ExpandableSection
                          toggleText="Options"
                          isExpanded={expandedRows.has(String(index))}
                          onToggle={() => toggleRowExpanded(index)}
                        >
                          <Stack hasGutter>
                            <StackItem>
                              <Controller
                                name={`outputFields.${index}.required` as const}
                                control={control}
                                render={({ field }) => (
                                  <Checkbox
                                    id={getFieldPathId(index, 'required')}
                                    label="Required"
                                    isChecked={field.value}
                                    onChange={(_event, checked) => field.onChange(checked)}
                                    description="Parent workflows can expect this field to always be present"
                                    isDisabled={isVersionView}
                                  />
                                )}
                              />
                            </StackItem>

                            <StackItem>
                              <FormGroup label="Description" fieldId={getFieldPathId(index, 'description')}>
                                <TextInput
                                  id={getFieldPathId(index, 'description')}
                                  {...register(`outputFields.${index}.description` as const)}
                                  placeholder="Describe this output field"
                                  isDisabled={isVersionView}
                                />
                              </FormGroup>
                            </StackItem>

                            <StackItem>
                              <FormGroup label="Type" fieldId={getFieldPathId(index, 'type')}>
                                <Controller
                                  name={`outputFields.${index}.type` as const}
                                  control={control}
                                  render={({ field }) => (
                                    <TypeaheadSelect
                                      id={getFieldPathId(index, 'type')}
                                      ariaLabel="Field type"
                                      options={[
                                        { value: 'string', label: 'String' },
                                        { value: 'number', label: 'Number' },
                                        { value: 'boolean', label: 'Boolean' },
                                        { value: 'object', label: 'Object' },
                                        { value: 'array', label: 'Array' },
                                      ]}
                                      selected={field.value ?? 'string'}
                                      onChange={(value) => field.onChange(value ?? 'string')}
                                      placeholder="Select type"
                                      isDisabled={isVersionView}
                                    />
                                  )}
                                />
                              </FormGroup>
                            </StackItem>
                          </Stack>
                        </ExpandableSection>
                      </StackItem>
                    </Stack>
                  </CardBody>
                </Card>
              </StackItem>
            )
          })}

          {!isVersionView && (
            <StackItem>
              <Button variant="link" icon={<RhUiAddIcon />} onClick={handleAddField} isInline>
                Add output field
              </Button>
            </StackItem>
          )}
        </>
      ) : (
        <>
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
                              Define the public fields the parent workflow can use. Map each field to a child step
                              output below.
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
                <Stack hasGutter>
                  <StackItem>
                    <Stack>
                      <StackItem>
                        <Title headingLevel="h4">Map output values</Title>
                      </StackItem>
                      <StackItem>
                        <Content component={ContentVariants.p}>
                          Choose the child step output that supplies each declared field. The value is available if that
                          step runs.
                        </Content>
                      </StackItem>
                    </Stack>
                  </StackItem>
                  {!hasValidOutputSchema && (
                    <StackItem>
                      <Alert
                        variant="info"
                        isInline
                        isPlain
                        title="Add output fields to the schema above to map their values"
                      />
                    </StackItem>
                  )}
                </Stack>
              </StackItem>
            </Stack>
          </StackItem>
        </>
      )}
    </Stack>
  )
}
