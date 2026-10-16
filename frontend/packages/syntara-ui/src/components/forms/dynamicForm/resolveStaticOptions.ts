import type { SynDynamicFormSelectOption } from '../SynDynamicForm.types'

import type { ResolvedOptionsSource, StaticOptionsSource } from './synDynamicFormFieldTypes'

export function resolveStaticOptions(
  source: StaticOptionsSource | ResolvedOptionsSource
): SynDynamicFormSelectOption[] {
  return source.values.map((option) => ({
    label: option.display_label,
    value: option.value,
  }))
}
