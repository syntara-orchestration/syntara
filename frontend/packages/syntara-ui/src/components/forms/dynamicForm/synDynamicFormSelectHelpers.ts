import type { SynDynamicFormSelectOption } from '../SynDynamicForm.types'

export type OptionScalarValue = string | number | boolean

export function optionKey(value: OptionScalarValue): string {
  return typeof value === 'string' ? value : JSON.stringify(value)
}

function isOptionScalar(value: unknown): value is OptionScalarValue {
  const kind = typeof value
  return kind === 'string' || kind === 'number' || kind === 'boolean'
}

export function getSelectedScalarValues(value: unknown, isMulti: boolean): OptionScalarValue[] {
  if (isMulti) {
    if (!Array.isArray(value)) {
      return []
    }
    return value.filter(isOptionScalar)
  }
  if (value === '' || value === null || value === undefined) {
    return []
  }
  if (isOptionScalar(value)) {
    return [value]
  }
  return []
}

export function getSelectedOptionLabels(
  options: readonly SynDynamicFormSelectOption[],
  selectedValues: OptionScalarValue[]
): string[] {
  const selectedKeys = new Set(selectedValues.map((value) => optionKey(value)))
  return options.filter((option) => selectedKeys.has(optionKey(option.value))).map((option) => option.label)
}

export function getSelectToggleLabel(selectedLabels: string[], placeholder: string, isMulti: boolean): string {
  if (selectedLabels.length === 0) {
    return placeholder
  }
  if (isMulti) {
    return selectedLabels.join(', ')
  }
  return selectedLabels[0] ?? placeholder
}
