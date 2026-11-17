import { FormFieldDisplayEnum, type FormFieldDisplay } from '@syntara/contracts'

export type FormPromptDefinitionField = {
  type: string
  value_name: string
  label: string
  required?: boolean
  display?: FormFieldDisplay
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

export function parseFormDefinitionFieldFromApi(value: unknown): FormPromptDefinitionField | null {
  if (!isRecord(value)) {
    return null
  }
  const { type, value_name, label, required, display } = value
  if (typeof type !== 'string' || typeof value_name !== 'string' || typeof label !== 'string') {
    return null
  }
  if (required !== undefined && typeof required !== 'boolean') {
    return null
  }
  if (
    display !== undefined &&
    display !== FormFieldDisplayEnum.SINGLE_LINE &&
    display !== FormFieldDisplayEnum.MULTI_LINE &&
    display !== FormFieldDisplayEnum.MASKED
  ) {
    return null
  }
  return {
    type,
    value_name,
    label,
    ...(required === undefined ? {} : { required }),
    ...(display === undefined ? {} : { display }),
  }
}
