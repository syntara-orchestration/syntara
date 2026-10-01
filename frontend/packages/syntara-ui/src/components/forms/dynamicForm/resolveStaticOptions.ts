import type { SynDynamicFormSelectOption } from '../SynDynamicForm.types'

import type { StaticOptionsSource } from './synDynamicFormFieldTypes'

export function resolveStaticOptions(source: StaticOptionsSource): SynDynamicFormSelectOption[] {
  return source.values.map((option) => ({
    label: option.display_label,
    value: option.value,
  }))
}
