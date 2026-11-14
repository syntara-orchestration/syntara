import {
  Button,
  Card,
  CardBody,
  Checkbox,
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
} from '@patternfly/react-core'
import { RhUiTrashIcon, RhUiWarningIcon } from '@patternfly/react-icons'
import { useState } from 'react'
import { Controller, useFormContext } from 'react-hook-form'
import type { Control, UseFormSetValue } from 'react-hook-form'

import { TypeaheadSelect } from '../../access/TypeaheadSelect'

import type { OutputSourceOption } from './SubWorkflowOutputSourceOptions'
import type { TriggerFormData } from './triggerFormSchema'

type OutputField = NonNullable<TriggerFormData['outputFields']>[number]
const OUTPUT_DESCRIPTION_GUIDANCE = 'Help parent workflow authors understand this value'

type Props = Readonly<{
  index: number
  row: OutputField
  sourceOptions: OutputSourceOption[]
  isVersionView: boolean
  isSourceConditional: (expression: string) => boolean
  outputNameError?: string
  onRowChange: (row: OutputField) => void
  onRemove: () => void
}>

function getFieldId(index: number, suffix: string) {
  return `subworkflow-output-${index}-${suffix}`
}

function getSelectedSourceLabel(source: OutputSourceOption | undefined, isUnavailable: boolean): string | undefined {
  if (source) return `${source.stepName} · ${source.fieldName}`
  return isUnavailable ? 'Unavailable in current workflow' : undefined
}

function getOutputSourceIssues({
  isConditional,
  isRequired,
  isUnavailable,
  isTypeMismatch,
  sourceType,
  outputType,
}: Readonly<{
  isConditional: boolean
  isRequired: boolean
  isUnavailable: boolean
  isTypeMismatch: boolean
  sourceType?: OutputSourceOption['type']
  outputType: OutputField['type']
}>): Array<{ message: string; variant: 'warning' | 'indeterminate' }> {
  const issues: Array<{ message: string; variant: 'warning' | 'indeterminate' }> = []
  if (isConditional) {
    issues.push({
      message: isRequired
        ? 'This step may not run on every path. If this required value is missing, the child run fails.'
        : 'This step may not run on every workflow path.',
      variant: isRequired ? 'warning' : 'indeterminate',
    })
  }
  if (isUnavailable) {
    issues.push({
      message: 'This saved source is unavailable. Choose an existing child step output.',
      variant: 'warning',
    })
  }
  if (isTypeMismatch && sourceType) {
    issues.push({
      message: `The saved output type (${outputType}) differs from the selected source type (${sourceType}). Review the output schema.`,
      variant: 'warning',
    })
  }
  return issues
}

function getInitialDescription(row: OutputField, sourceOptions: OutputSourceOption[]): string {
  const hasAutoSourceDescription = sourceOptions.some((source) => source.sourceDescription === row.description)
  return row.description?.trim() && !hasAutoSourceDescription ? row.description : OUTPUT_DESCRIPTION_GUIDANCE
}

type OutputMappingFieldProps = Readonly<{
  control: Control<TriggerFormData>
  setValue: UseFormSetValue<TriggerFormData>
  index: number
  row: OutputField
  sourceOptions: OutputSourceOption[]
  isVersionView: boolean
  isSourceConditional: (expression: string) => boolean
  onRowChange: (row: OutputField) => void
}>

function renderOutputMappingField({
  control,
  setValue,
  index,
  row,
  sourceOptions,
  isVersionView,
  isSourceConditional,
  onRowChange,
}: OutputMappingFieldProps) {
  const selectedSource = sourceOptions.find((source) => source.expression === row.expression?.trim())
  const isSourceUnavailable = Boolean(row.expression && !selectedSource)
  const isSourceTypeMismatch = Boolean(
    selectedSource && row.type !== 'unknown' && selectedSource.type !== 'unknown' && selectedSource.type !== row.type
  )
  const selectedSourceLabel = getSelectedSourceLabel(selectedSource, isSourceUnavailable)
  const sourceIssues = getOutputSourceIssues({
    isConditional: Boolean(row.expression && isSourceConditional(row.expression)),
    isRequired: row.required,
    isUnavailable: isSourceUnavailable,
    isTypeMismatch: isSourceTypeMismatch,
    sourceType: selectedSource?.type,
    outputType: row.type,
  })

  return (
    <StackItem>
      <FormGroup label="Select a child step output" fieldId={getFieldId(index, 'expression')}>
        <Controller
          name={`outputFields.${index}.expression` as const}
          control={control}
          render={({ field }) => (
            <>
              <TypeaheadSelect
                id={getFieldId(index, 'expression')}
                ariaLabel={`Choose child output for ${row.path || `output ${index + 1}`}`}
                options={sourceOptions.map((option) => ({
                  value: option.expression,
                  label: option.fieldName,
                  group: option.stepName,
                  description: option.sourceDescription,
                }))}
                selected={field.value ?? ''}
                selectedLabel={selectedSourceLabel}
                onChange={(value) => {
                  const option = sourceOptions.find((candidate) => candidate.expression === value)
                  if (!option) {
                    field.onChange('')
                    onRowChange({ ...row, expression: '' })
                    return
                  }
                  field.onChange(value)
                  setValue(`outputFields.${index}.type`, option.type, {
                    shouldDirty: true,
                    shouldValidate: true,
                  })
                  if (!row.path?.trim()) {
                    setValue(`outputFields.${index}.path`, option.fieldName, {
                      shouldDirty: true,
                      shouldValidate: true,
                    })
                  }
                  const description = getInitialDescription(row, sourceOptions)
                  onRowChange({
                    ...row,
                    expression: value,
                    type: option.type,
                    description,
                    ...(!row.path?.trim() ? { path: option.fieldName } : {}),
                  })
                  setValue(`outputFields.${index}.description`, description, {
                    shouldDirty: true,
                    shouldValidate: true,
                  })
                }}
                placeholder="Choose a step output…"
                searchPromptThreshold={20}
                isRequired={row.required}
                isDisabled={isVersionView}
              />
              <FormHelperText>
                <HelperText>
                  <HelperTextItem>
                    This output supplies {row.path || 'the returned field'} to the parent. Type is inferred; the value
                    is available if the selected step runs.
                  </HelperTextItem>
                  {sourceIssues.map((issue) => (
                    <HelperTextItem key={issue.message} variant={issue.variant} icon={<RhUiWarningIcon />}>
                      {issue.message}
                    </HelperTextItem>
                  ))}
                </HelperText>
              </FormHelperText>
            </>
          )}
        />
      </FormGroup>
    </StackItem>
  )
}

export function SubWorkflowSimpleOutputFieldCard({
  index,
  row,
  sourceOptions,
  isVersionView,
  isSourceConditional,
  outputNameError,
  onRowChange,
  onRemove,
}: Props) {
  const { control, setValue, register } = useFormContext<TriggerFormData>()
  const [isExpanded, setIsExpanded] = useState(false)

  return (
    <StackItem>
      <Card isCompact>
        <CardBody>
          <Stack hasGutter>
            <StackItem>
              <Flex>
                <FlexItem flex={{ default: 'flex_1' }}>
                  <FormGroup label="Output name" fieldId={getFieldId(index, 'path')}>
                    <TextInput
                      id={getFieldId(index, 'path')}
                      {...register(`outputFields.${index}.path` as const)}
                      value={row.path}
                      onChange={(_event, value) => {
                        setValue(`outputFields.${index}.path`, value, { shouldDirty: true, shouldValidate: true })
                        onRowChange({ ...row, path: value })
                      }}
                      placeholder="e.g. status"
                      isDisabled={isVersionView}
                      validated={outputNameError ? 'error' : 'default'}
                    />
                    {outputNameError && (
                      <FormHelperText>
                        <HelperText>
                          <HelperTextItem variant="error">{outputNameError}</HelperTextItem>
                        </HelperText>
                      </FormHelperText>
                    )}
                    {!outputNameError && (
                      <FormHelperText>
                        <HelperText>
                          <HelperTextItem>Use dot notation for nested output objects.</HelperTextItem>
                        </HelperText>
                      </FormHelperText>
                    )}
                  </FormGroup>
                </FlexItem>
                <FlexItem alignSelf={{ default: 'alignSelfCenter' }}>
                  <Button
                    variant="plain"
                    icon={<RhUiTrashIcon />}
                    onClick={onRemove}
                    aria-label={`Remove output ${row.path || index + 1}`}
                    isDisabled={isVersionView}
                  />
                </FlexItem>
              </Flex>
            </StackItem>

            {renderOutputMappingField({
              control,
              setValue,
              index,
              row,
              sourceOptions,
              isVersionView,
              isSourceConditional,
              onRowChange,
            })}

            <StackItem>
              <Stack>
                <StackItem>
                  <Controller
                    name={`outputFields.${index}.required` as const}
                    control={control}
                    render={({ field }) => (
                      <Checkbox
                        id={getFieldId(index, 'required')}
                        label="Required output"
                        isChecked={field.value}
                        onChange={(_event, checked) => {
                          field.onChange(checked)
                          onRowChange({ ...row, required: checked })
                        }}
                        isDisabled={isVersionView}
                      />
                    )}
                  />
                </StackItem>
                <StackItem>
                  <FormHelperText>
                    <HelperText>
                      <HelperTextItem>
                        Required marks this value as part of the output contract. Workflow routing determines whether
                        its source step runs.
                      </HelperTextItem>
                    </HelperText>
                  </FormHelperText>
                </StackItem>
              </Stack>
            </StackItem>

            <StackItem>
              <ExpandableSection
                toggleText="Field options"
                isExpanded={isExpanded}
                onToggle={() => setIsExpanded((expanded) => !expanded)}
              >
                <Stack hasGutter>
                  <StackItem>
                    <FormGroup label="Description (optional)" fieldId={getFieldId(index, 'description')}>
                      <TextInput
                        id={getFieldId(index, 'description')}
                        {...register(`outputFields.${index}.description` as const)}
                        value={row.description ?? ''}
                        onChange={(_event, value) => {
                          setValue(`outputFields.${index}.description`, value, {
                            shouldDirty: true,
                            shouldValidate: true,
                          })
                          onRowChange({ ...row, description: value })
                        }}
                        placeholder="Help parent workflow authors understand this value"
                        isDisabled={isVersionView}
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
}
