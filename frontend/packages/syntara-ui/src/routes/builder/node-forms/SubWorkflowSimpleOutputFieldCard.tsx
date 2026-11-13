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

import { TypeaheadSelect } from '../../access/TypeaheadSelect'

import type { OutputSourceOption } from './SubWorkflowOutputSourceOptions'
import type { TriggerFormData } from './triggerFormSchema'

type OutputField = NonNullable<TriggerFormData['outputFields']>[number]

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
  const selectedSource = sourceOptions.find((source) => source.expression === row.expression)

  return (
    <StackItem>
      <Card isCompact>
        <CardBody>
          <Stack hasGutter>
            <StackItem>
              <Flex>
                <FlexItem flex={{ default: 'flex_1' }}>
                  <FormGroup label="Name returned to parent" fieldId={getFieldId(index, 'path')}>
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

            <StackItem>
              <FormGroup label="Select a child step output" fieldId={getFieldId(index, 'expression')}>
                <Controller
                  name={`outputFields.${index}.expression` as const}
                  control={control}
                  render={({ field }) => {
                    const isConditional = field.value ? isSourceConditional(field.value) : false
                    return (
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
                          selectedLabel={
                            selectedSource ? `${selectedSource.stepName} · ${selectedSource.fieldName}` : undefined
                          }
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
                            setValue(`outputFields.${index}.description`, option.sourceDescription, {
                              shouldDirty: true,
                              shouldValidate: true,
                            })
                            if (!row.path?.trim()) {
                              setValue(`outputFields.${index}.path`, option.fieldName, {
                                shouldDirty: true,
                                shouldValidate: true,
                              })
                            }
                            onRowChange({
                              ...row,
                              expression: value,
                              type: option.type,
                              description: option.sourceDescription,
                              ...(!row.path?.trim() ? { path: option.fieldName } : {}),
                            })
                          }}
                          placeholder="Choose a step output…"
                          searchPromptThreshold={20}
                          isDisabled={isVersionView}
                        />
                        <FormHelperText>
                          <HelperText>
                            <HelperTextItem>
                              This output supplies {row.path || 'the returned field'} to the parent. Type is inferred;
                              the value is available if the selected step runs.
                            </HelperTextItem>
                            {isConditional && row.required && (
                              <HelperTextItem variant="warning" icon={<RhUiWarningIcon />}>
                                This step may not run on every path. If this required value is missing, the child run
                                fails.
                              </HelperTextItem>
                            )}
                            {isConditional && !row.required && (
                              <HelperTextItem variant="indeterminate" icon={<RhUiWarningIcon />}>
                                This step may not run on every workflow path.
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
                toggleText="Field options"
                isExpanded={isExpanded}
                onToggle={() => setIsExpanded((expanded) => !expanded)}
              >
                <Stack hasGutter>
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
