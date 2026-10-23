import { TextArea, TextInput } from '@patternfly/react-core'
import { useCallback, useState } from 'react'
import type { ReactNode } from 'react'

import { buildContextExpression, buildExpression } from '../../utils/expressions/templateBuilder'
import {
  DRAG_TYPE_CONTEXT,
  DRAG_TYPE_FIELD,
  EXPRESSION_FIELD_PLACEHOLDER,
  isDragData,
} from '../expressions/expressionFieldDrag'
import { FormFieldError, FormFieldHintOrError } from '../FormFieldError'

import styles from './ExpressionFieldInput.module.css'
import { validateExpressionSyntax } from './expressionFieldSyntax'

export type ExpressionFieldInputProps = {
  id: string
  value: string
  onChange: (value: string) => void
  onBlur?: () => void
  name?: string
  placeholder?: string
  isRequired?: boolean
  isDisabled?: boolean
  /** Renders a multiline text area for JSON-like expression values. */
  isMultiline?: boolean
  /** External validation message; takes precedence over inline syntax validation. */
  externalError?: string | null
  hint?: string
  hintPlacement?: 'before-input' | 'after-input'
  afterInput?: ReactNode
  /** Notifies parent wrappers when drag-and-drop highlight state changes. */
  onDropTargetChange?: (active: boolean) => void
}

type ExpressionFieldControlProps = {
  id: string
  value: string
  onTextInputChange: (event: React.FormEvent<HTMLInputElement>, value: string) => void
  onTextAreaChange: (event: React.FormEvent<HTMLTextAreaElement>, value: string) => void
  onBlur?: () => void
  name?: string
  onDragOver: (event: React.DragEvent) => void
  onDragLeave: () => void
  onDrop: (event: React.DragEvent) => void
  placeholder: string
  isRequired: boolean
  validated: 'default' | 'error'
  isDisabled?: boolean
  describedBy?: string
  isDropTarget: boolean
  isMultiline: boolean
}

function ExpressionFieldControl({
  id,
  value,
  onTextInputChange,
  onTextAreaChange,
  onBlur,
  name,
  onDragOver,
  onDragLeave,
  onDrop,
  placeholder,
  isRequired,
  validated,
  isDisabled,
  describedBy,
  isDropTarget,
  isMultiline,
}: Readonly<ExpressionFieldControlProps>) {
  const className = isDropTarget ? styles.dropTargetActive : undefined
  const dropTarget = isDropTarget ? 'active' : 'inactive'

  if (isMultiline) {
    return (
      <TextArea
        id={id}
        value={value}
        onChange={onTextAreaChange}
        onBlur={onBlur}
        name={name}
        onDragOver={onDragOver}
        onDragLeave={onDragLeave}
        onDrop={onDrop}
        placeholder={placeholder}
        isRequired={isRequired}
        validated={validated}
        isDisabled={isDisabled}
        aria-describedby={describedBy}
        className={className}
        data-drop-target={dropTarget}
        resizeOrientation="vertical"
      />
    )
  }

  return (
    <TextInput
      id={id}
      value={value}
      onChange={onTextInputChange}
      onBlur={onBlur}
      name={name}
      onDragOver={onDragOver}
      onDragLeave={onDragLeave}
      onDrop={onDrop}
      placeholder={placeholder}
      isRequired={isRequired}
      validated={validated}
      isDisabled={isDisabled}
      aria-describedby={describedBy}
      className={className}
      data-drop-target={dropTarget}
    />
  )
}

/**
 * Shared expression input with drag-and-drop token support and inline
 * `${...}` syntax validation. It renders a text input or multiline text area
 * and is used by `SynExpressionField` and builder `ExpressionFormField`.
 */
export function ExpressionFieldInput({
  id,
  value,
  onChange,
  onBlur,
  name,
  placeholder = EXPRESSION_FIELD_PLACEHOLDER,
  isRequired = false,
  isDisabled,
  isMultiline = false,
  externalError,
  hint,
  hintPlacement = 'after-input',
  afterInput,
  onDropTargetChange,
}: Readonly<ExpressionFieldInputProps>) {
  const [isDropTarget, setIsDropTarget] = useState(false)
  const syntaxError = validateExpressionSyntax(value)
  const displayError = externalError ?? syntaxError
  const hasError = Boolean(displayError)
  const helperTextId = `${id}-helper-text`

  const handleTextInputChange = useCallback(
    (_event: React.FormEvent<HTMLInputElement>, newValue: string) => {
      onChange(newValue)
    },
    [onChange]
  )
  const handleTextAreaChange = useCallback(
    (_event: React.FormEvent<HTMLTextAreaElement>, newValue: string) => {
      onChange(newValue)
    },
    [onChange]
  )

  const handleDragOver = useCallback(
    (event: React.DragEvent) => {
      event.preventDefault()
      setIsDropTarget(true)
      onDropTargetChange?.(true)
    },
    [onDropTargetChange]
  )

  const handleDragLeave = useCallback(() => {
    setIsDropTarget(false)
    onDropTargetChange?.(false)
  }, [onDropTargetChange])

  const handleDrop = useCallback(
    (event: React.DragEvent) => {
      event.preventDefault()
      setIsDropTarget(false)
      onDropTargetChange?.(false)
      const raw = event.dataTransfer.getData('application/json')
      if (!raw) return
      let data: unknown
      try {
        data = JSON.parse(raw)
      } catch {
        return
      }
      if (!isDragData(data)) return
      if (data.type === DRAG_TYPE_FIELD) {
        onChange(value + buildExpression({ nodeId: data.nodeId, fieldPath: data.fieldPath }))
      } else if (data.type === DRAG_TYPE_CONTEXT) {
        onChange(value + buildContextExpression(data.contextPath))
      }
    },
    [onChange, onDropTargetChange, value]
  )

  return (
    <>
      {!displayError && hint && hintPlacement === 'before-input' && (
        <FormFieldHintOrError id={helperTextId} hint={hint} />
      )}
      <ExpressionFieldControl
        id={id}
        value={value}
        onTextInputChange={handleTextInputChange}
        onTextAreaChange={handleTextAreaChange}
        onBlur={onBlur}
        name={name}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        placeholder={placeholder}
        isRequired={isRequired}
        validated={hasError ? 'error' : 'default'}
        isDisabled={isDisabled}
        describedBy={displayError || hint ? helperTextId : undefined}
        isDropTarget={isDropTarget}
        isMultiline={isMultiline}
      />
      {afterInput}
      {displayError ? (
        <FormFieldError id={helperTextId} message={displayError} />
      ) : (
        hint && hintPlacement === 'after-input' && <FormFieldHintOrError id={helperTextId} hint={hint} />
      )}
    </>
  )
}
