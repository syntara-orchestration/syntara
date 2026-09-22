import { TextInput } from '@patternfly/react-core'
import { useCallback, useState } from 'react'

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
  isDisabled?: boolean
  /** External validation message; takes precedence over inline syntax validation. */
  externalError?: string | null
  hint?: string
  /** Notifies parent wrappers when drag-and-drop highlight state changes. */
  onDropTargetChange?: (active: boolean) => void
}

/**
 * Shared expression text input with drag-and-drop token support and inline
 * `${...}` syntax validation. Used by `SynExpressionField` and builder
 * `ExpressionFormField`.
 */
export function ExpressionFieldInput({
  id,
  value,
  onChange,
  onBlur,
  name,
  placeholder = EXPRESSION_FIELD_PLACEHOLDER,
  isDisabled,
  externalError,
  hint,
  onDropTargetChange,
}: Readonly<ExpressionFieldInputProps>) {
  const [isDropTarget, setIsDropTarget] = useState(false)
  const syntaxError = validateExpressionSyntax(value)
  const displayError = externalError ?? syntaxError
  const hasError = Boolean(displayError)

  const handleChange = useCallback(
    (_event: React.FormEvent<HTMLInputElement>, newValue: string) => {
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
      <TextInput
        id={id}
        value={value}
        onChange={handleChange}
        onBlur={onBlur}
        name={name}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        placeholder={placeholder}
        validated={hasError ? 'error' : 'default'}
        isDisabled={isDisabled}
        className={isDropTarget ? styles.dropTargetActive : undefined}
        data-drop-target={isDropTarget ? 'active' : 'inactive'}
      />
      {displayError ? <FormFieldError message={displayError} /> : hint && <FormFieldHintOrError hint={hint} />}
    </>
  )
}
