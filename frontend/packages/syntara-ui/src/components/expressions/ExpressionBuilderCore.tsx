/**
 * Core expression builder component with state management
 * Uses useReducer for managing nested expression tree
 */

import { MenuToggle, type MenuToggleElement, SelectList, SelectOption, Stack, StackItem } from '@patternfly/react-core'
import { useCallback, useReducer, useEffect, useRef, useState } from 'react'

import { createDefaultGroup, createDefaultCondition } from '../../utils/expressions/defaults'
import { parseExpression } from '../../utils/expressions/parser'
import { serializeExpression } from '../../utils/expressions/serializer'
import type { Expression, ExpressionNode, ExpressionGroup as ExpressionGroupType } from '../../utils/expressions/types'
import { SynSelect } from '../SynSelect'

import { ExpressionGroup } from './ExpressionGroup'
import { ExpressionRawEditor } from './ExpressionRawEditor'
import { prepareRootNode } from './prepareRootNode'

type VisualExpressionEditorProps = {
  group: ExpressionGroupType
  onUpdateRoot: (root: ExpressionGroupType) => void
  error?: boolean
}

function VisualExpressionEditor({ group, onUpdateRoot, error }: VisualExpressionEditorProps) {
  return (
    <ExpressionGroup
      group={group}
      onChange={(updates) => onUpdateRoot({ ...group, ...updates })}
      onUpdateChild={(index, node) => {
        const updatedChildren = [...group.children]
        updatedChildren[index] = node
        onUpdateRoot({ ...group, children: updatedChildren })
      }}
      onRemoveChild={(index) => {
        const updatedChildren = group.children.filter((_, i) => i !== index)
        onUpdateRoot({
          ...group,
          children: updatedChildren.length > 0 ? updatedChildren : [createDefaultCondition()],
        })
      }}
      onAddCondition={() => {
        onUpdateRoot({ ...group, children: [...group.children, createDefaultCondition()] })
      }}
      onAddGroup={() => {
        onUpdateRoot({ ...group, children: [...group.children, createDefaultGroup()] })
      }}
      level={0}
      error={error}
    />
  )
}

type ExpressionBuilderCoreProps = {
  /** Current expression value (template string) */
  value: string
  /** Callback when expression changes. Additional args preserve state for round-trip. */
  onChange: (value: string, expressionTree?: Expression, mode?: 'visual' | 'raw') => void
  /** Optional: provide an initial expression tree to avoid lossy string parsing */
  initialExpression?: Expression
  /** Optional: restore the editor mode from a previous session */
  initialMode?: 'visual' | 'raw'
  /** Placeholder text */
  placeholder?: string
  /** Whether to show error state */
  error?: boolean
  /** ID for the component (for label association) */
  id?: string
  /** aria-labelledby for accessibility */
  'aria-labelledby'?: string
}

type EditorMode = 'visual' | 'raw'

type BuilderState = {
  expression: Expression

  mode: EditorMode
  rawValue: string
}

type BuilderAction =
  | { type: 'SET_EXPRESSION'; payload: Expression }
  | { type: 'SET_RAW_VALUE'; payload: string }
  | { type: 'TOGGLE_MODE' }
  | { type: 'UPDATE_ROOT'; payload: ExpressionNode | null }

function builderReducer(state: BuilderState, action: BuilderAction): BuilderState {
  switch (action.type) {
    case 'SET_EXPRESSION':
      return {
        ...state,
        expression: action.payload,
        rawValue: serializeExpression(action.payload),
      }

    case 'SET_RAW_VALUE':
      return {
        ...state,
        rawValue: action.payload,
      }

    case 'TOGGLE_MODE': {
      if (state.mode === 'visual') {
        // Switching to raw mode
        return {
          ...state,
          mode: 'raw',
          rawValue: serializeExpression(state.expression),
        }
      } else {
        // Switching to visual mode
        const parsed = parseExpression(state.rawValue)
        // Allow switching to visual mode even if parsing fails (empty or invalid)
        // Show default empty group if no valid expression
        return {
          ...state,
          mode: 'visual',
          expression: parsed.root ? parsed : { root: createDefaultGroup() },
        }
      }
    }

    case 'UPDATE_ROOT':
      return {
        ...state,
        expression: { root: action.payload },
      }

    default:
      return state
  }
}

/**
 * Expression builder core component
 *
 * Manages the expression tree state and provides visual/raw mode toggle
 * Follows the ScheduleBuilderFields pattern for external sync
 */
export function ExpressionBuilderCore(props: ExpressionBuilderCoreProps) {
  const {
    value,
    onChange,
    initialExpression: providedExpression,
    initialMode: providedMode,
    error,
    placeholder,
    id,
    'aria-labelledby': ariaLabelledBy,
  } = props

  // Initialize state — use provided mode if available (preserves user's last choice).
  // Fall back to provided expression tree (preserves nesting structure),
  // then string parsing (which can lose same-operator nesting).
  const [state, dispatch] = useReducer(builderReducer, value, (initialValue): BuilderState => {
    if (providedMode === 'raw') {
      return {
        expression: providedExpression?.root ? providedExpression : { root: createDefaultGroup() },
        mode: 'raw',
        rawValue: initialValue,
      }
    }

    const expression = providedExpression?.root ? providedExpression : parseExpression(initialValue)
    const initialMode: EditorMode = providedMode ?? (!expression.root && initialValue ? 'raw' : 'visual')

    return {
      expression: expression.root ? expression : { root: createDefaultGroup() },
      mode: initialMode,
      rawValue: initialValue,
    }
  })

  // Track previous values to detect external changes
  const prevValueRef = useRef(value)
  const lastEmittedRef = useRef<string | undefined>(undefined)

  // Update local state and mode when value prop changes from external source
  useEffect(() => {
    if (value !== prevValueRef.current && value !== lastEmittedRef.current) {
      const parsed = parseExpression(value)
      if (parsed.root) {
        dispatch({ type: 'SET_EXPRESSION', payload: parsed })
      } else if (value) {
        dispatch({ type: 'SET_EXPRESSION', payload: { root: createDefaultGroup() } })
        dispatch({ type: 'SET_RAW_VALUE', payload: value })
      } else {
        dispatch({ type: 'SET_EXPRESSION', payload: { root: createDefaultGroup() } })
        dispatch({ type: 'SET_RAW_VALUE', payload: '' })
      }
    }
    prevValueRef.current = value
  }, [value])

  // Emit changes to parent — value, expression tree, and mode
  const prevModeRef = useRef(state.mode)
  useEffect(() => {
    const newValue = state.mode === 'visual' ? serializeExpression(state.expression) : state.rawValue
    const modeChanged = state.mode !== prevModeRef.current
    prevModeRef.current = state.mode

    if (newValue !== value && newValue !== lastEmittedRef.current) {
      lastEmittedRef.current = newValue
      const tree = state.mode === 'visual' ? state.expression : { root: null }
      onChange(newValue, tree, state.mode)
    } else if (modeChanged) {
      const tree = state.mode === 'visual' ? state.expression : { root: null }
      onChange(value, tree, state.mode)
    }
  }, [state.expression, state.rawValue, state.mode, onChange, value])

  const [isModeOpen, setIsModeOpen] = useState(false)

  const handleModeSelect = useCallback(
    (_event: React.MouseEvent | undefined, value: string | number | undefined) => {
      const selected = String(value)
      if ((selected === 'visual' && state.mode === 'raw') || (selected === 'raw' && state.mode === 'visual')) {
        dispatch({ type: 'TOGGLE_MODE' })
      }
      setIsModeOpen(false)
    },
    [state.mode]
  )

  const modeToggleRef = useCallback(
    (toggleRef: React.Ref<MenuToggleElement>) => (
      <MenuToggle
        ref={toggleRef}
        onClick={() => setIsModeOpen((prev) => !prev)}
        isExpanded={isModeOpen}
        isFullWidth
        aria-label="Expression editor mode"
      >
        {state.mode === 'visual' ? 'Visual expression builder' : 'Custom expression'}
      </MenuToggle>
    ),
    [isModeOpen, state.mode]
  )

  const handleRawChange = (rawValue: string) => {
    dispatch({ type: 'SET_RAW_VALUE', payload: rawValue })
  }

  const rootNode = prepareRootNode(state.expression)

  return (
    <Stack
      hasGutter
      id={id}
      aria-label={ariaLabelledBy ? undefined : 'Expression builder'}
      aria-labelledby={ariaLabelledBy}
      role="group"
    >
      <StackItem>
        <SynSelect
          isOpen={isModeOpen}
          onSelect={handleModeSelect}
          onOpenChange={setIsModeOpen}
          toggle={modeToggleRef}
          selected={state.mode}
        >
          <SelectList aria-label="Expression editor mode">
            <SelectOption value="visual">Visual expression builder</SelectOption>
            <SelectOption value="raw">Custom expression</SelectOption>
          </SelectList>
        </SynSelect>
      </StackItem>

      <StackItem>
        <div
          style={{
            borderRadius: 'var(--pf-t--global--border-radius--default)',
            backgroundColor: 'var(--pf-t--global--color--surface--primary)',
            width: '100%',
            padding: 'var(--pf-t--global--spacer--sm)',
          }}
        >
          {state.mode === 'visual' ? (
            <VisualExpressionEditor
              group={rootNode}
              onUpdateRoot={(root) => dispatch({ type: 'UPDATE_ROOT', payload: root })}
              error={error}
            />
          ) : (
            <ExpressionRawEditor
              value={state.rawValue}
              onChange={handleRawChange}
              error={error}
              placeholder={placeholder}
            />
          )}
        </div>
      </StackItem>
    </Stack>
  )
}
