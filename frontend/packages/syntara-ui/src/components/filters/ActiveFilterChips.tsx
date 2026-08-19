import { LabelGroup, ToolbarItem } from '@patternfly/react-core'
import type { ReactNode } from 'react'

import type { FilterConfig, FilterFieldDefinition, FilterOperator } from '../../types/filters'
import { formatDateChipValue } from '../../utils/dateUtils'
import { NxLabel } from '../labels/NxLabel'
import { WorkflowName } from '../WorkflowName'

/** User-applied filter values use outlined compact labels. */
function ActiveFilterValueLabel({ children, onClose }: Readonly<{ children: ReactNode; onClose: () => void }>) {
  return (
    <NxLabel variant="outline" onClose={onClose}>
      {children}
    </NxLabel>
  )
}

/** Resolves a filter value to a display label from field options or getOptionLabel. */
function resolveFilterOptionDisplayLabel(field: FilterFieldDefinition | undefined, value: unknown): string | null {
  if (field?.options) {
    const option = field.options.find((opt) => String(opt.value) === String(value))
    if (option) {
      return option.label
    }
  }
  if (field?.getOptionLabel) {
    const label = field.getOptionLabel(String(value))
    if (label) {
      return label
    }
  }
  return null
}

function getScalarFilterDisplayValue(
  field: FilterFieldDefinition | undefined,
  filter: FilterConfig,
  operator: FilterOperator
): string {
  const resolved = resolveFilterOptionDisplayLabel(field, filter.value)
  if (resolved) {
    return resolved
  }

  if (operator === 'gte' || operator === 'gt') {
    const formatted = formatDateChipValue(String(filter.value))
    return `From: ${formatted || String(filter.value)}`
  }
  if (operator === 'lte' || operator === 'lt') {
    const formatted = formatDateChipValue(String(filter.value))
    return `To: ${formatted || String(filter.value)}`
  }

  return String(filter.value)
}

/** Label for one multi-select value; matches scalar option resolution, then raw value. */
function getArrayFilterValueDisplayLabel(field: FilterFieldDefinition | undefined, val: string): string {
  return resolveFilterOptionDisplayLabel(field, val) ?? val
}

type ArrayFilterValueLabelsProps = {
  field: FilterFieldDefinition | undefined
  filter: FilterConfig
  operator: FilterOperator
  values: string[]
  onChipRemove: (fieldKey: string, operator?: FilterOperator, value?: string) => void
}

function ArrayFilterValueLabels({ field, filter, operator, values, onChipRemove }: ArrayFilterValueLabelsProps) {
  return values.map((val) => {
    const displayLabel = getArrayFilterValueDisplayLabel(field, val)
    return (
      <ActiveFilterValueLabel
        key={`${filter.key}-${operator}-${val}`}
        onClose={() => onChipRemove(filter.key, filter.operator, val)}
      >
        {displayLabel}
      </ActiveFilterValueLabel>
    )
  })
}

/**
 * Props for ActiveFilterChips component
 */
type ActiveFilterChipsProps = {
  /** Current active filters */
  filters: FilterConfig[]
  /** Filter field definitions */
  fieldDefinitions: FilterFieldDefinition[]
  /** Callback when chip is removed. Pass value to remove a single item from a multi-select array. */
  onChipRemove: (fieldKey: string, operator?: FilterOperator, value?: string) => void
  /** Callback when all chips for a category are removed */
  onCategoryRemove?: (fieldKey: string) => void
}

/**
 * Displays active filter chips grouped by field name
 */
export function ActiveFilterChips({
  filters,
  fieldDefinitions,
  onChipRemove,
  onCategoryRemove,
}: ActiveFilterChipsProps) {
  if (filters.length === 0) return null

  // Group filters by field key
  const filtersByField = filters.reduce(
    (acc, filter) => {
      if (!acc[filter.key]) {
        acc[filter.key] = []
      }
      acc[filter.key].push(filter)
      return acc
    },
    {} as Record<string, FilterConfig[]>
  )

  return (
    <ToolbarItem>
      {Object.entries(filtersByField).map(([fieldKey, fieldFilters]) => {
        const field = fieldDefinitions.find((f) => f.key === fieldKey)
        const categoryName = field?.label ?? fieldKey

        const handleCategoryClose = () => {
          onCategoryRemove?.(fieldKey)
        }

        return (
          <LabelGroup
            key={fieldKey}
            categoryName={categoryName}
            isClosable
            closeBtnAriaLabel={`Remove all ${categoryName} filters`}
            onClick={(event) => {
              const target = event.target as HTMLElement
              const closeButton = target.closest('button[aria-label*="Remove all"]')
              if (closeButton) {
                handleCategoryClose()
              }
            }}
            aria-label={categoryName}
          >
            {fieldFilters.flatMap((filter) => {
              const operator = filter.operator ?? 'eq'

              if (Array.isArray(filter.value)) {
                return (
                  <ArrayFilterValueLabels
                    key={`${filter.key}-array-${operator}`}
                    field={field}
                    filter={filter}
                    operator={operator}
                    values={filter.value}
                    onChipRemove={onChipRemove}
                  />
                )
              }

              const uniqueKey = `${filter.key}-${operator}`

              if (filter.key === 'workflow_id' && typeof filter.value === 'string') {
                return (
                  <ActiveFilterValueLabel key={uniqueKey} onClose={() => onChipRemove(filter.key, filter.operator)}>
                    <WorkflowName workflowId={filter.value} />
                  </ActiveFilterValueLabel>
                )
              }

              const displayValue = getScalarFilterDisplayValue(field, filter, operator)

              return (
                <ActiveFilterValueLabel key={uniqueKey} onClose={() => onChipRemove(filter.key, filter.operator)}>
                  {displayValue}
                </ActiveFilterValueLabel>
              )
            })}
          </LabelGroup>
        )
      })}
    </ToolbarItem>
  )
}
