import { Button, Flex, FlexItem, FormGroup, TextInput } from '@patternfly/react-core'
import { RhUiAddIcon, RhUiTrashIcon } from '@patternfly/react-icons'
import { useCallback, useMemo } from 'react'

/**
 * Single label key-value pair
 */
export type LabelPair = {
  /** Unique identifier for React key prop */
  id: string
  /** Label key */
  key: string
  /** Label value */
  value: string
}

/**
 * Props for LabelFilter component
 */
export type LabelFilterProps = {
  /** Display label for the filter */
  label: string
  /** Current label filters */
  labels?: Record<string, string>
  /** Callback when labels change */
  onChange: (labelParams: Record<string, string>) => void
}

/**
 * Props for LabelPairRow component
 */
type LabelPairRowProps = {
  /** Label pair data */
  pair: LabelPair
  /** Index for accessibility labels */
  index: number
  /** Callback when key changes */
  onKeyChange: (event: React.FormEvent<HTMLInputElement>, value: string) => void
  /** Callback when value changes */
  onValueChange: (event: React.FormEvent<HTMLInputElement>, value: string) => void
  /** Callback when remove button clicked */
  onRemove: () => void
  /** Whether remove button should be disabled */
  isRemoveDisabled: boolean
}

/**
 * Single label key-value pair row
 */
function LabelPairRow({ pair, index, onKeyChange, onValueChange, onRemove, isRemoveDisabled }: LabelPairRowProps) {
  return (
    <Flex gap={{ default: 'gapSm' }} alignItems={{ default: 'alignItemsCenter' }}>
      <FlexItem flex={{ default: 'flex_1' }}>
        <TextInput
          type="text"
          id={`label-key-${pair.id}`}
          name={`label-key-${pair.id}`}
          aria-label={`Label key ${index + 1}`}
          placeholder="Key"
          value={pair.key}
          onChange={onKeyChange}
        />
      </FlexItem>
      <FlexItem flex={{ default: 'flex_1' }}>
        <TextInput
          type="text"
          id={`label-value-${pair.id}`}
          name={`label-value-${pair.id}`}
          aria-label={`Label value ${index + 1}`}
          placeholder="Value"
          value={pair.value}
          onChange={onValueChange}
        />
      </FlexItem>
      <FlexItem>
        <Button
          variant="plain"
          aria-label={`Remove label ${index + 1}`}
          onClick={onRemove}
          isDisabled={isRemoveDisabled}
          icon={<RhUiTrashIcon />}
        />
      </FlexItem>
    </Flex>
  )
}

/**
 * Label filter component for key-value pair filtering
 *
 * Fully controlled component - parent manages labels via props.
 * Uses PatternFly TextInput for key-value pair input.
 * Supports multiple label filters with AND logic.
 * Emits label parameters in labels[key]=value format.
 *
 * @example
 * ```tsx
 * <LabelFilter
 *   label="Labels"
 *   labels={{ environment: 'prod', team: 'platform' }}
 *   onChange={(labelParams) => handleLabelChange(labelParams)}
 * />
 * ```
 */
export function LabelFilter({ label, labels = {}, onChange }: LabelFilterProps) {
  // Derive label pairs from props - fully controlled, no local state
  // Use stable IDs to prevent React reconciliation issues during editing
  const labelPairs = useMemo((): LabelPair[] => {
    const entries = Object.entries(labels)
    if (entries.length > 0) {
      return entries.map(([labelKey, value]) => {
        // The labelKey from props is either:
        // 1. A real label key (for filled pairs)
        // 2. A temp ID like 'empty' or 'empty-123' (for partially-filled pairs)
        // If it looks like a temp ID (starts with 'empty'), treat key field as empty
        const isTempId = labelKey.startsWith('empty')
        return {
          id: labelKey,
          key: isTempId ? '' : labelKey,
          value,
        }
      })
    }
    // Always show at least one empty pair for adding labels
    return [{ id: 'empty', key: '', value: '' }]
  }, [labels])

  // Emit label parameters
  const emitLabels = useCallback(
    (pairs: LabelPair[]) => {
      // Build params including partially-filled pairs so parent can preserve UI state
      const params: Record<string, string> = {}

      pairs.forEach((pair) => {
        // Use the pair ID to maintain stable identity across edits
        // Once a pair is fully filled (both key and value), use the actual key
        // While editing, use the temp ID to preserve React key stability
        const isFullyFilled = pair.key.trim() && pair.value.trim()
        const paramKey = isFullyFilled ? pair.key.trim() : pair.id
        params[`labels[${paramKey}]`] = pair.value
      })

      onChange(params)
    },
    [onChange]
  )

  // Handle key change - emit immediately with updated key
  const handleKeyChange = useCallback(
    (id: string) => (_event: React.FormEvent<HTMLInputElement>, newKey: string) => {
      const updated = labelPairs.map((pair) => (pair.id === id ? { ...pair, key: newKey } : pair))
      emitLabels(updated)
    },
    [labelPairs, emitLabels]
  )

  // Handle value change - emit immediately with updated value
  const handleValueChange = useCallback(
    (id: string) => (_event: React.FormEvent<HTMLInputElement>, newValue: string) => {
      const updated = labelPairs.map((pair) => (pair.id === id ? { ...pair, value: newValue } : pair))
      emitLabels(updated)
    },
    [labelPairs, emitLabels]
  )

  // Add new empty label pair
  const handleAdd = useCallback(() => {
    const usedIds = new Set(labelPairs.map((p) => p.id))
    let emptyId: string
    if (usedIds.has('empty')) {
      let n = 1
      while (usedIds.has(`empty-${n}`)) {
        n += 1
      }
      emptyId = `empty-${n}`
    } else {
      emptyId = 'empty'
    }
    // Create new labels from current pairs + new empty pair
    const newLabels: Record<string, string> = {}
    labelPairs.forEach((pair) => {
      newLabels[pair.id] = pair.value
    })
    newLabels[emptyId] = ''

    // Emit params including empty pairs so parent can track UI state
    const params: Record<string, string> = {}
    Object.entries(newLabels).forEach(([key, value]) => {
      params[`labels[${key}]`] = value
    })
    onChange(params)
  }, [labelPairs, onChange])

  // Remove label pair
  const handleRemove = useCallback(
    (id: string) => {
      const updated = labelPairs.filter((pair) => pair.id !== id)
      emitLabels(updated)
    },
    [labelPairs, emitLabels]
  )

  return (
    <FormGroup label={label}>
      <Flex direction={{ default: 'column' }} gap={{ default: 'gapSm' }}>
        {labelPairs.map((pair, index) => (
          <FlexItem key={pair.id}>
            <LabelPairRow
              pair={pair}
              index={index}
              onKeyChange={handleKeyChange(pair.id)}
              onValueChange={handleValueChange(pair.id)}
              onRemove={() => handleRemove(pair.id)}
              isRemoveDisabled={labelPairs.length === 1}
            />
          </FlexItem>
        ))}
        <FlexItem>
          <Button variant="link" icon={<RhUiAddIcon />} onClick={handleAdd}>
            Add label
          </Button>
        </FlexItem>
      </Flex>
    </FormGroup>
  )
}
