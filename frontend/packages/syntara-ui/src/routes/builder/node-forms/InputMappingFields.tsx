import {
  Flex,
  FlexItem,
  FormGroup,
  HelperText,
  HelperTextItem,
  Stack,
  StackItem,
  TextArea,
  Title,
} from '@patternfly/react-core'
import type { ReactElement } from 'react'

import { EXPRESSION_FIELD_PLACEHOLDER } from '../../../components/expressions/expressionFieldDrag'
import { ExpressionFormField } from '../panels/fields/ExpressionFormField'

import styles from './InputMappingFields.module.css'
import type { InvocationInputField } from './invocationSchemaUtils'

export type InputMappingFieldsProps = {
  fields: InvocationInputField[]
  values: Record<string, unknown>
  onChange: (values: Record<string, unknown>) => void
  freeformJson: string
  onFreeformJsonChange: (value: string) => void
  sectionTitle?: string
  isDisabled?: boolean
  labelHelp?: ReactElement
  error?: string
}

function formatValue(value: unknown): string {
  if (typeof value === 'string') return value
  if (value === undefined || value === null) return ''
  return JSON.stringify(value)
}

function updateValue(values: Record<string, unknown>, name: string, value: string) {
  return { ...values, [name]: value }
}

function getInputFieldHint(field: InvocationInputField): string | undefined {
  const description = field.description?.trim().replace(/[.\s]+$/, '')
  return description || undefined
}

function renderSchemaInputField(
  field: InvocationInputField,
  index: number,
  context: {
    values: Record<string, unknown>
    onChange: (values: Record<string, unknown>) => void
    isDisabled: boolean
  }
): ReactElement {
  const { values, onChange, isDisabled } = context
  const value = formatValue(Object.hasOwn(values, field.name) ? values[field.name] : undefined)
  const fieldId = `child-input-${index}`

  return (
    <StackItem key={field.name}>
      <ExpressionFormField
        id={fieldId}
        label={field.name}
        value={value}
        onChange={(nextValue) => onChange(updateValue(values, field.name, nextValue))}
        placeholder={EXPRESSION_FIELD_PLACEHOLDER}
        isRequired={field.required}
        isDisabled={isDisabled}
        hint={getInputFieldHint(field)}
        hintPlacement="before-input"
        isMultiline={field.type === 'object' || field.type === 'array'}
      />
    </StackItem>
  )
}

/** Schema-driven values for child workflow inputs, with a JSON fallback when no schema is declared. */
function InputMappingFields({
  fields,
  values,
  onChange,
  freeformJson,
  onFreeformJsonChange,
  sectionTitle = 'Input Mapping',
  isDisabled = false,
  labelHelp,
  error,
}: Readonly<InputMappingFieldsProps>) {
  if (fields.length === 0) {
    return (
      <FormGroup label={`${sectionTitle} (JSON)`} labelHelp={labelHelp} fieldId="input-mapping-json">
        <TextArea
          id="input-mapping-json"
          aria-label="Input Mapping JSON"
          value={freeformJson}
          onChange={(_event, value) => onFreeformJsonChange(value)}
          isDisabled={isDisabled}
          validated={error ? 'error' : 'default'}
          resizeOrientation="vertical"
        />
        <HelperText>
          <HelperTextItem variant={error ? 'error' : 'default'}>
            {error ?? 'Enter a JSON object with child input values.'}
          </HelperTextItem>
        </HelperText>
      </FormGroup>
    )
  }

  return (
    <Stack hasGutter>
      <StackItem>
        <Flex alignItems={{ default: 'alignItemsCenter' }} gap={{ default: 'gapSm' }}>
          <FlexItem>
            <Title headingLevel="h3" size="md" className={styles.sectionTitle}>
              {sectionTitle}
            </Title>
          </FlexItem>
          {labelHelp && <FlexItem>{labelHelp}</FlexItem>}
        </Flex>
      </StackItem>
      {error && (
        <StackItem>
          <HelperText>
            <HelperTextItem variant="error">{error}</HelperTextItem>
          </HelperText>
        </StackItem>
      )}
      {fields.map((field, index) => renderSchemaInputField(field, index, { values, onChange, isDisabled }))}
    </Stack>
  )
}

export { InputMappingFields }
