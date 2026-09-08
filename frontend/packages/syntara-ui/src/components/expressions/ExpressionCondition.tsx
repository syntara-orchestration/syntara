/**
 * Individual condition component for the expression builder
 * Renders a single condition row with variable, operator, value inputs
 */

import {
  Card,
  CardBody,
  Checkbox,
  Flex,
  FlexItem,
  FormGroup,
  FormHelperText,
  HelperText,
  HelperTextItem,
  MenuToggle,
  type MenuToggleElement,
  SelectGroup,
  SelectList,
  SelectOption,
  TextInput,
  Button,
  Stack,
  StackItem,
} from '@patternfly/react-core'
import { RhUiTrashIcon } from '@patternfly/react-icons'
import { useCallback, useState } from 'react'

import { isUnaryOperator, OPERATOR_LABELS, OPERATOR_GROUPS } from '../../utils/expressions/defaults'
import type { ExpressionCondition as ExpressionConditionType, ComparisonOperator } from '../../utils/expressions/types'
import { SynSelect } from '../SynSelect'

import { HelpPopover } from './HelpPopover'

const MAX_VARIABLE_LENGTH = 256
const VARIABLE_PATTERN = /^[a-zA-Z_][a-zA-Z0-9_.]*$/
const RESERVED_NAMES = ['__proto__', 'constructor', 'prototype']

function isValidVariableRef(value: string): boolean {
  if (value.length > MAX_VARIABLE_LENGTH || !VARIABLE_PATTERN.test(value)) return false
  return !value.split('.').some((part) => RESERVED_NAMES.includes(part))
}

const FieldHelp = () => (
  <HelpPopover
    ariaLabel="Field help"
    headerContent="Field"
    bodyContent={
      <div>
        The data point you want to evaluate. You can type a value manually or drag and drop a variable (like a status
        code, ID, or name) from a previous step's output.
      </div>
    }
  />
)

const OperatorHelp = () => (
  <HelpPopover
    ariaLabel="Operator help"
    headerContent="Operator"
    bodyContent={
      <div>
        The logical test to apply to your field. Common options include "is equal to," "contains," "is greater than," or
        "is empty."
      </div>
    }
  />
)

const ValueHelp = () => (
  <HelpPopover
    ariaLabel="Value help"
    headerContent="Value"
    bodyContent={
      <div>
        The specific criteria you are testing against. This is what the "Field" will be compared to using your chosen
        "Operator."
      </div>
    }
  />
)

const NotHelp = () => (
  <HelpPopover
    ariaLabel="NOT operator help"
    headerContent="Not"
    bodyContent={
      <div>
        Inverse the logic of this specific condition. When checked, the condition will evaluate as true only if the
        specified criteria are not met.
      </div>
    }
  />
)

type ExpressionConditionProps = {
  /** The condition data */
  condition: ExpressionConditionType
  /** Callback when condition is updated */
  onChange: (updates: Partial<ExpressionConditionType>) => void
  /** Callback when condition should be removed */
  onRemove?: () => void
  /** Whether to show error state */
  error?: boolean
  /** Per-field error messages displayed inline under each field */
  fieldErrors?: { variable?: string; value?: string }
}

/**
 * Individual condition row component
 *
 * Renders inputs for:
 * - NOT checkbox (optional negation) - in separate row
 * - Variable input (e.g., "trigger.age")
 * - Operator select (unified list)
 * - Value input (e.g., "18") - hidden for unary operators (exists, isEmpty, etc.)
 * - Remove button (if onRemove provided)
 */
export function ExpressionCondition(props: ExpressionConditionProps) {
  const { condition, onChange, onRemove, error, fieldErrors } = props

  const [isOperatorOpen, setIsOperatorOpen] = useState(false)
  const [isFieldFocused, setIsFieldFocused] = useState(false)
  const [editingValue, setEditingValue] = useState('')
  const [localFieldError, setLocalFieldError] = useState<string | null>(null)

  const handleFieldFocus = useCallback(() => {
    setIsFieldFocused(true)
    setEditingValue(condition.variable ? `\${${condition.variable}}` : '')
  }, [condition.variable])

  const handleFieldBlur = useCallback(() => {
    setIsFieldFocused(false)
    const stripped = editingValue.replace(/^\$\{/, '').replace(/\}$/, '')
    if (stripped && !isValidVariableRef(stripped)) {
      setLocalFieldError('Invalid variable name. Use letters, numbers, dots, and underscores (e.g. trigger.age).')
      return
    }
    setLocalFieldError(null)
    if (stripped !== condition.variable) {
      onChange({ variable: stripped })
    }
  }, [editingValue, condition.variable, onChange])

  const handleFieldDrop = useCallback(
    (e: React.DragEvent<HTMLInputElement>) => {
      e.preventDefault()
      const text = e.dataTransfer.getData('text/plain')
      if (!text) return
      const stripped = text.replace(/^\$\{/, '').replace(/\}$/, '')
      if (!stripped || !isValidVariableRef(stripped)) return
      setEditingValue(`\${${stripped}}`)
      onChange({ variable: stripped })
    },
    [onChange]
  )

  const blurredValue = condition.variable ? `\${${condition.variable}}` : ''
  const fieldDisplayValue = isFieldFocused ? editingValue : blurredValue

  const fieldValidated = (() => {
    if (localFieldError) return 'error' as const
    if (!error) return 'default' as const
    const currentValue = isFieldFocused ? editingValue.replace(/^\$\{/, '').replace(/\}$/, '') : condition.variable
    return !currentValue.trim() ? ('error' as const) : ('default' as const)
  })()

  const displayFieldError = localFieldError ?? fieldErrors?.variable

  const handleOperatorSelect = useCallback(
    (_event: React.MouseEvent | undefined, value: string | number | undefined) => {
      const newOp = String(value) as ComparisonOperator
      onChange({
        operator: newOp,
        ...(isUnaryOperator(newOp) && { value: '' }),
      })
      setIsOperatorOpen(false)
    },
    [onChange]
  )

  const operatorToggle = useCallback(
    (toggleRef: React.Ref<MenuToggleElement>) => (
      <MenuToggle
        ref={toggleRef}
        onClick={() => setIsOperatorOpen((prev) => !prev)}
        isExpanded={isOperatorOpen}
        isFullWidth
        aria-label="Comparison operator"
        id={`operator-${condition.id}`}
      >
        {OPERATOR_LABELS[condition.operator]}
      </MenuToggle>
    ),
    [isOperatorOpen, condition.operator, condition.id]
  )

  return (
    <Card style={{ borderRadius: 'var(--pf-t--global--border-radius--pill)' }}>
      <CardBody style={{ position: 'relative' }}>
        {/* Remove button - positioned at top right */}
        {onRemove && (
          <div
            style={{
              position: 'absolute',
              top: 'var(--pf-t--global--spacer--sm)',
              right: 'var(--pf-t--global--spacer--sm)',
            }}
          >
            <Button variant="plain" isDanger onClick={onRemove} aria-label="Remove condition">
              <RhUiTrashIcon />
            </Button>
          </div>
        )}

        <Stack hasGutter>
          {/* NOT checkbox at top */}
          <StackItem>
            <Flex spaceItems={{ default: 'spaceItemsXs' }} alignItems={{ default: 'alignItemsCenter' }}>
              <FlexItem>
                <Checkbox
                  id={`not-${condition.id}`}
                  label="Not"
                  isChecked={condition.negate ?? false}
                  onChange={(_event, checked) => onChange({ negate: checked })}
                  aria-label="Negate condition"
                />
              </FlexItem>
              <FlexItem>
                <NotHelp />
              </FlexItem>
            </Flex>
          </StackItem>

          {/* Field */}
          <StackItem>
            <FormGroup label="Field" labelHelp={<FieldHelp />} isRequired fieldId={`field-${condition.id}`}>
              <TextInput
                id={`field-${condition.id}`}
                value={fieldDisplayValue}
                onChange={(_event, value) => {
                  setEditingValue(value)
                  if (localFieldError) setLocalFieldError(null)
                }}
                onFocus={handleFieldFocus}
                onBlur={handleFieldBlur}
                onDrop={handleFieldDrop}
                onDragOver={(e) => e.preventDefault()}
                placeholder="e.g. ${trigger.age}"
                style={{ fontFamily: 'monospace', fontSize: 'var(--pf-t--global--font--size--body--sm)' }}
                validated={fieldValidated}
              />
              {displayFieldError && (
                <FormHelperText>
                  <HelperText>
                    <HelperTextItem variant="error">{displayFieldError}</HelperTextItem>
                  </HelperText>
                </FormHelperText>
              )}
            </FormGroup>
          </StackItem>

          {/* Operator */}
          <StackItem>
            <FormGroup label="Operator" labelHelp={<OperatorHelp />} isRequired fieldId={`operator-${condition.id}`}>
              <SynSelect
                isOpen={isOperatorOpen}
                onSelect={handleOperatorSelect}
                onOpenChange={setIsOperatorOpen}
                toggle={operatorToggle}
                selected={condition.operator}
              >
                <SelectList aria-label="Comparison operator">
                  {OPERATOR_GROUPS.map((opGroup) => (
                    <SelectGroup key={opGroup.label} label={opGroup.label}>
                      {opGroup.operators.map((op) => (
                        <SelectOption key={op} value={op}>
                          {OPERATOR_LABELS[op]}
                        </SelectOption>
                      ))}
                    </SelectGroup>
                  ))}
                </SelectList>
              </SynSelect>
            </FormGroup>
          </StackItem>

          {/* Value (only for binary operators) */}
          {!isUnaryOperator(condition.operator) && (
            <StackItem>
              <FormGroup label="Value" labelHelp={<ValueHelp />} isRequired fieldId={`value-${condition.id}`}>
                <TextInput
                  id={`value-${condition.id}`}
                  value={condition.value}
                  onChange={(_event, value) => onChange({ value })}
                  placeholder="Enter or drag and drop value"
                  style={{ fontFamily: 'monospace', fontSize: 'var(--pf-t--global--font--size--body--sm)' }}
                  validated={error && !condition.value.trim() ? 'error' : 'default'}
                />
                {fieldErrors?.value && (
                  <FormHelperText>
                    <HelperText>
                      <HelperTextItem variant="error">{fieldErrors.value}</HelperTextItem>
                    </HelperText>
                  </FormHelperText>
                )}
              </FormGroup>
            </StackItem>
          )}
        </Stack>
      </CardBody>
    </Card>
  )
}
