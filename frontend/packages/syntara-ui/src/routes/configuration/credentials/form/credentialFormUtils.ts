import type { UseFormSetError } from 'react-hook-form'

import type { CredentialType } from '../credentialConstants'
import { ENCRYPTED_SENTINEL } from '../credentialConstants'

import type { CredentialFormData } from './credentialFormSchema'
import type { FieldDefinition } from './DynamicFieldRenderer'

export type TypeInputs = {
  fields: FieldDefinition[]
  required: string[]
  mutually_exclusive: string[][]
  mutually_exclusive_labels: string[]
  mutually_exclusive_help: string
  required_one_of: string[][]
  required_together: string[][]
}

export type ExclusiveGroup = {
  fieldIds: string[]
  label: string
}

/** Extract the dynamic field definitions, required field IDs, and field constraints from a credential type's inputs schema. */
export function getTypeInputs(credType: CredentialType): TypeInputs {
  const inputs = credType.inputs as Record<string, unknown>
  return {
    fields: (inputs?.fields as FieldDefinition[]) ?? [],
    required: (inputs?.required as string[]) ?? [],
    mutually_exclusive: (inputs?.mutually_exclusive as string[][]) ?? [],
    mutually_exclusive_labels: (inputs?.mutually_exclusive_labels as string[]) ?? [],
    mutually_exclusive_help: (inputs?.mutually_exclusive_help as string) ?? '',
    required_one_of: (inputs?.required_one_of as string[][]) ?? [],
    required_together: (inputs?.required_together as string[][]) ?? [],
  }
}

/** Build default input values for a credential type, using each field's `default` when defined. */
export function getDefaultInputs(credType: CredentialType | undefined): Record<string, unknown> {
  if (!credType) return {}
  const typeInputs = getTypeInputs(credType)
  const defaults: Record<string, unknown> = {}
  for (const field of typeInputs.fields) {
    if (field.default != null) {
      defaults[field.id] = field.default
    }
  }
  return defaults
}

/** Validate a required dynamic field in edit mode — skips untouched secret fields to preserve existing encrypted values. */
export function validateEditModeRequiredDynamicField(
  requiredId: string,
  val: unknown,
  field: FieldDefinition | undefined,
  touchedSecrets: Set<string>,
  setError: UseFormSetError<CredentialFormData>
): boolean {
  const isSecret = field?.secret === true
  if (isSecret) {
    if (touchedSecrets.has(requiredId) && (val == null || val === '')) {
      setError(`inputs.${requiredId}`, { message: `${field?.label ?? requiredId} is required` })
      return false
    }
    return true
  }
  if (val == null || val === '') {
    setError(`inputs.${requiredId}`, { message: `${field?.label ?? requiredId} is required` })
    return false
  }
  return true
}

/** Validate a required dynamic field in create mode — all required fields must have a non-empty value. */
export function validateCreateModeRequiredDynamicField(
  requiredId: string,
  val: unknown,
  field: FieldDefinition | undefined,
  setError: UseFormSetError<CredentialFormData>
): boolean {
  if (val == null || val === '') {
    setError(`inputs.${requiredId}`, { message: `${field?.label ?? requiredId} is required` })
    return false
  }
  return true
}

/** Build ExclusiveGroup objects from TypeInputs.mutually_exclusive, using custom labels when available. */
export function buildExclusiveGroups(typeInputs: TypeInputs): ExclusiveGroup[] {
  if (typeInputs.mutually_exclusive.length === 0) return []

  return typeInputs.mutually_exclusive.map((group, index) => {
    const customLabel = typeInputs.mutually_exclusive_labels[index]
    if (customLabel) return { fieldIds: group, label: customLabel }

    const labels = group.map((fieldId) => {
      const field = typeInputs.fields.find((f) => f.id === fieldId)
      return field?.label ?? fieldId
    })
    return { fieldIds: group, label: labels.join(' + ') }
  })
}

/** Detect which exclusive group has existing values, for edit mode initialization. Returns 0 if no group has values. */
export function detectActiveGroupIndex(groups: ExclusiveGroup[], inputs: Record<string, unknown>): number {
  for (let i = 0; i < groups.length; i++) {
    const hasValues = groups[i].fieldIds.some((id) => {
      const val = inputs[id]
      return val != null && val !== ''
    })
    if (hasValues) return i
  }
  return 0
}

/** Return only the fields that should be visible given the active exclusive group. */
export function getVisibleFields(typeInputs: TypeInputs, activeGroupIndex: number): FieldDefinition[] {
  if (typeInputs.mutually_exclusive.length === 0) return typeInputs.fields

  const allExclusiveFieldIds = getAllExclusiveFieldIds(typeInputs)
  const activeGroup = typeInputs.mutually_exclusive[activeGroupIndex]
  const activeFieldIds = new Set(activeGroup ?? [])

  return typeInputs.fields.filter((field) => !allExclusiveFieldIds.has(field.id) || activeFieldIds.has(field.id))
}

/** Return the index in visibleFields where the auth method selector should be inserted (before the first exclusive field). */
export function getAuthMethodInsertIndex(visibleFields: FieldDefinition[], typeInputs: TypeInputs): number {
  if (typeInputs.mutually_exclusive.length === 0) return -1
  const allExclusiveFieldIds = getAllExclusiveFieldIds(typeInputs)
  const index = visibleFields.findIndex((f) => allExclusiveFieldIds.has(f.id))
  return index === -1 ? visibleFields.length : index
}

/** Validate required_together constraints — if any field in a group has a value, all fields in that group must. */
export function validateFieldConstraints(
  typeInputs: TypeInputs,
  inputs: Record<string, unknown>,
  setError: UseFormSetError<CredentialFormData>
): boolean {
  let valid = true

  for (const group of typeInputs.required_together) {
    const filledFields = group.filter((id) => {
      const val = inputs[id]
      return val != null && val !== ''
    })

    if (filledFields.length > 0 && filledFields.length < group.length) {
      const missingFields = group.filter((id) => !filledFields.includes(id))
      for (const missingId of missingFields) {
        const field = typeInputs.fields.find((f) => f.id === missingId)
        setError(`inputs.${missingId}`, { message: `${field?.label ?? missingId} is required` })
      }
      valid = false
    }
  }
  return valid
}

/** Compute the initial activeGroupIndex for a modal reset. */
export function computeInitialGroupIndex(
  credentialToEdit: { credential_type_id: string; inputs?: unknown } | null | undefined,
  types: CredentialType[]
): number {
  if (!credentialToEdit) return 0
  const editType = types.find((t) => t.id === credentialToEdit.credential_type_id)
  if (!editType) return 0
  const editTypeInputs = getTypeInputs(editType)
  const editGroups = buildExclusiveGroups(editTypeInputs)
  if (editGroups.length === 0) return 0
  return detectActiveGroupIndex(editGroups, credentialToEdit.inputs as Record<string, unknown>)
}

/** Return a Set of all field IDs across all mutually exclusive groups. */
export function getAllExclusiveFieldIds(typeInputs: TypeInputs): Set<string> {
  return new Set(typeInputs.mutually_exclusive.flat())
}

type ValidateDynamicFieldsOptions = {
  typeInputs: TypeInputs | null
  inputs: Record<string, unknown>
  visibleFields: FieldDefinition[]
  isEditMode: boolean
  touchedSecrets: Set<string>
}

function validateRequiredField(
  fieldId: string,
  options: ValidateDynamicFieldsOptions,
  setError: UseFormSetError<CredentialFormData>
): boolean {
  const { typeInputs, inputs, isEditMode, touchedSecrets } = options
  const val = inputs[fieldId]
  const field = typeInputs?.fields.find((f) => f.id === fieldId)

  if (isEditMode) {
    return validateEditModeRequiredDynamicField(fieldId, val, field, touchedSecrets, setError)
  }
  return validateCreateModeRequiredDynamicField(fieldId, val, field, setError)
}

/** Validate all dynamic required fields plus field constraints. */
export function validateAllDynamicFields(
  options: ValidateDynamicFieldsOptions,
  setError: UseFormSetError<CredentialFormData>
): boolean {
  const { typeInputs, visibleFields } = options
  if (!typeInputs) return true
  let valid = true

  const visibleFieldIds = new Set(visibleFields.map((f) => f.id))

  for (const requiredId of typeInputs.required) {
    if (!visibleFieldIds.has(requiredId)) continue
    if (!validateRequiredField(requiredId, options, setError)) valid = false
  }

  if (!validateFieldConstraints(typeInputs, options.inputs, setError)) {
    valid = false
  }

  for (const group of typeInputs.required_one_of) {
    if (!group.every((id) => visibleFieldIds.has(id))) continue
    for (const fieldId of group) {
      if (!validateRequiredField(fieldId, options, setError)) valid = false
    }
  }

  return valid
}

/** Build edit-mode inputs: preserve encrypted sentinel for untouched secret fields. */
export function buildEditInputs(
  currentInputs: Record<string, unknown>,
  typeInputs: TypeInputs | null,
  touchedSecrets: Set<string>
): Record<string, unknown> {
  if (!typeInputs) return currentInputs
  const result = { ...currentInputs }
  for (const field of typeInputs.fields) {
    if (field.secret) {
      const val = result[field.id]
      if (!touchedSecrets.has(field.id) || val === '' || val == null || val === ENCRYPTED_SENTINEL) {
        result[field.id] = ENCRYPTED_SENTINEL
      }
    }
  }
  return result
}

/** Remove fields belonging to hidden exclusive groups from the inputs before submission. */
export function stripHiddenGroupFields(
  formInputs: Record<string, unknown>,
  typeInputs: TypeInputs | null,
  visibleFields: FieldDefinition[]
): Record<string, unknown> {
  if (!typeInputs || typeInputs.mutually_exclusive.length === 0) return formInputs
  const visibleFieldIds = new Set(visibleFields.map((f) => f.id))
  const exclusiveFieldIds = getAllExclusiveFieldIds(typeInputs)
  const result = { ...formInputs }
  for (const fieldId of Object.keys(result)) {
    if (!visibleFieldIds.has(fieldId) && exclusiveFieldIds.has(fieldId)) {
      delete result[fieldId]
    }
  }
  return result
}
