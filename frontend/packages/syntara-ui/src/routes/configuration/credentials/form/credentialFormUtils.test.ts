import type { UseFormSetError } from 'react-hook-form'
import { describe, expect, it, vi } from 'vitest'

import type { CredentialType } from '../credentialConstants'
import { ENCRYPTED_SENTINEL } from '../credentialConstants'

import type { CredentialFormData } from './credentialFormSchema'
import {
  buildEditInputs,
  buildExclusiveGroups,
  detectActiveGroupIndex,
  getAllExclusiveFieldIds,
  getAuthMethodInsertIndex,
  getDefaultInputs,
  getTypeInputs,
  getVisibleFields,
  stripHiddenGroupFields,
  validateAllDynamicFields,
  validateCreateModeRequiredDynamicField,
  validateEditModeRequiredDynamicField,
  validateFieldConstraints,
} from './credentialFormUtils'
import type { FieldDefinition } from './DynamicFieldRenderer'

function makeCredentialType(overrides: Partial<CredentialType> & { inputs: unknown }): CredentialType {
  return { id: 'type-1', name: 'Test Type', ...overrides }
}

function makeSetError() {
  return vi.fn<UseFormSetError<CredentialFormData>>()
}

describe('getTypeInputs', () => {
  it('returns fields and required arrays from inputs', () => {
    const fields: FieldDefinition[] = [
      { id: 'token', label: 'Token', type: 'string' },
      { id: 'host', label: 'Host', type: 'string' },
    ]
    const credType = makeCredentialType({ inputs: { fields, required: ['token'] } })

    const result = getTypeInputs(credType)

    expect(result.fields).toEqual(fields)
    expect(result.required).toEqual(['token'])
  })

  it('returns empty arrays when inputs has no fields or required', () => {
    const credType = makeCredentialType({ inputs: {} })

    const result = getTypeInputs(credType)

    expect(result.fields).toEqual([])
    expect(result.required).toEqual([])
  })

  it('returns empty arrays when inputs is null-like', () => {
    const credType = makeCredentialType({ inputs: null as unknown as Record<string, unknown> })

    const result = getTypeInputs(credType)

    expect(result.fields).toEqual([])
    expect(result.required).toEqual([])
  })

  it('extracts constraint keys from inputs', () => {
    const credType = makeCredentialType({
      inputs: {
        fields: [],
        required: [],
        mutually_exclusive: [['oauth_token'], ['username', 'password']],
        required_one_of: [['oauth_token'], ['username', 'password']],
        required_together: [['username', 'password']],
      },
    })

    const result = getTypeInputs(credType)

    expect(result.mutually_exclusive).toEqual([['oauth_token'], ['username', 'password']])
    expect(result.required_one_of).toEqual([['oauth_token'], ['username', 'password']])
    expect(result.required_together).toEqual([['username', 'password']])
  })

  it('defaults constraint keys to empty arrays when absent', () => {
    const credType = makeCredentialType({ inputs: { fields: [], required: [] } })

    const result = getTypeInputs(credType)

    expect(result.mutually_exclusive).toEqual([])
    expect(result.required_one_of).toEqual([])
    expect(result.required_together).toEqual([])
  })
})

describe('getDefaultInputs', () => {
  it('returns empty object for undefined type', () => {
    expect(getDefaultInputs(undefined)).toEqual({})
  })

  it('returns defaults from field definitions', () => {
    const credType = makeCredentialType({
      inputs: {
        fields: [
          { id: 'provider', label: 'Provider', type: 'string', default: 'openai' },
          { id: 'token', label: 'Token', type: 'string' },
          { id: 'verify', label: 'Verify', type: 'boolean', default: true },
        ],
        required: [],
      },
    })

    const result = getDefaultInputs(credType)

    expect(result).toEqual({ provider: 'openai', verify: true })
  })

  it('returns empty object when no fields have defaults', () => {
    const credType = makeCredentialType({
      inputs: {
        fields: [{ id: 'token', label: 'Token', type: 'string' }],
        required: [],
      },
    })

    expect(getDefaultInputs(credType)).toEqual({})
  })
})

describe('validateCreateModeRequiredDynamicField', () => {
  it('returns true for non-empty value', () => {
    const setError = makeSetError()
    const field: FieldDefinition = { id: 'token', label: 'Token', type: 'string' }

    const result = validateCreateModeRequiredDynamicField('token', 'my-token', field, setError)

    expect(result).toBe(true)
    expect(setError).not.toHaveBeenCalled()
  })

  it('returns false and sets error for null value', () => {
    const setError = makeSetError()
    const field: FieldDefinition = { id: 'token', label: 'Token', type: 'string' }

    const result = validateCreateModeRequiredDynamicField('token', null, field, setError)

    expect(result).toBe(false)
    expect(setError).toHaveBeenCalledWith('inputs.token', { message: 'Token is required' })
  })

  it('returns false and sets error for empty string', () => {
    const setError = makeSetError()
    const field: FieldDefinition = { id: 'token', label: 'Token', type: 'string' }

    const result = validateCreateModeRequiredDynamicField('token', '', field, setError)

    expect(result).toBe(false)
    expect(setError).toHaveBeenCalledWith('inputs.token', { message: 'Token is required' })
  })

  it('uses field id as fallback when field is undefined', () => {
    const setError = makeSetError()

    const result = validateCreateModeRequiredDynamicField('api_key', null, undefined, setError)

    expect(result).toBe(false)
    expect(setError).toHaveBeenCalledWith('inputs.api_key', { message: 'api_key is required' })
  })
})

describe('validateEditModeRequiredDynamicField', () => {
  it('returns true for non-empty non-secret value', () => {
    const setError = makeSetError()
    const field: FieldDefinition = { id: 'host', label: 'Host', type: 'string' }

    const result = validateEditModeRequiredDynamicField('host', 'example.com', field, new Set(), setError)

    expect(result).toBe(true)
    expect(setError).not.toHaveBeenCalled()
  })

  it('returns false for empty non-secret value', () => {
    const setError = makeSetError()
    const field: FieldDefinition = { id: 'host', label: 'Host', type: 'string' }

    const result = validateEditModeRequiredDynamicField('host', '', field, new Set(), setError)

    expect(result).toBe(false)
    expect(setError).toHaveBeenCalledWith('inputs.host', { message: 'Host is required' })
  })

  it('returns true for untouched secret field regardless of value', () => {
    const setError = makeSetError()
    const field: FieldDefinition = { id: 'token', label: 'Token', type: 'string', secret: true }

    const result = validateEditModeRequiredDynamicField('token', '', field, new Set(), setError)

    expect(result).toBe(true)
    expect(setError).not.toHaveBeenCalled()
  })

  it('returns false for touched secret field with empty value', () => {
    const setError = makeSetError()
    const field: FieldDefinition = { id: 'token', label: 'Token', type: 'string', secret: true }
    const touchedSecrets = new Set(['token'])

    const result = validateEditModeRequiredDynamicField('token', '', field, touchedSecrets, setError)

    expect(result).toBe(false)
    expect(setError).toHaveBeenCalledWith('inputs.token', { message: 'Token is required' })
  })

  it('returns true for touched secret field with non-empty value', () => {
    const setError = makeSetError()
    const field: FieldDefinition = { id: 'token', label: 'Token', type: 'string', secret: true }
    const touchedSecrets = new Set(['token'])

    const result = validateEditModeRequiredDynamicField('token', 'new-value', field, touchedSecrets, setError)

    expect(result).toBe(true)
    expect(setError).not.toHaveBeenCalled()
  })

  it('returns false for null non-secret value', () => {
    const setError = makeSetError()
    const field: FieldDefinition = { id: 'host', label: 'Host', type: 'string' }

    const result = validateEditModeRequiredDynamicField('host', null, field, new Set(), setError)

    expect(result).toBe(false)
    expect(setError).toHaveBeenCalledWith('inputs.host', { message: 'Host is required' })
  })
})

const aapFields: FieldDefinition[] = [
  { id: 'username', label: 'Username', type: 'string' },
  { id: 'password', label: 'Password', type: 'string', secret: true },
  { id: 'oauth_token', label: 'OAuth Token', type: 'string', secret: true },
]

const aapTypeInputs = {
  fields: aapFields,
  required: [],
  mutually_exclusive: [['oauth_token'], ['username', 'password']],
  mutually_exclusive_labels: ['OAuth2 Token', 'Basic Auth'],
  mutually_exclusive_help:
    'Basic Auth authenticates with username and password. OAuth2 Token uses a personal access token.',
  required_one_of: [['oauth_token'], ['username', 'password']],
  required_together: [['username', 'password']],
}

describe('buildExclusiveGroups', () => {
  it('uses custom labels when mutually_exclusive_labels is provided', () => {
    const groups = buildExclusiveGroups(aapTypeInputs)

    expect(groups).toEqual([
      { fieldIds: ['oauth_token'], label: 'OAuth2 Token' },
      { fieldIds: ['username', 'password'], label: 'Basic Auth' },
    ])
  })

  it('falls back to derived labels when no custom labels', () => {
    const typeInputs = {
      ...aapTypeInputs,
      mutually_exclusive_labels: [] as string[],
    }

    const groups = buildExclusiveGroups(typeInputs)

    expect(groups).toEqual([
      { fieldIds: ['oauth_token'], label: 'OAuth Token' },
      { fieldIds: ['username', 'password'], label: 'Username + Password' },
    ])
  })

  it('returns empty array when no mutually_exclusive groups', () => {
    const typeInputs = {
      fields: aapFields,
      required: [],
      mutually_exclusive: [],
      mutually_exclusive_labels: [],
      mutually_exclusive_help: '',
      required_one_of: [],
      required_together: [],
    }

    expect(buildExclusiveGroups(typeInputs)).toEqual([])
  })

  it('falls back to field ID when field definition not found', () => {
    const typeInputs = {
      fields: [],
      required: [],
      mutually_exclusive: [['unknown_field']],
      mutually_exclusive_labels: [],
      mutually_exclusive_help: '',
      required_one_of: [],
      required_together: [],
    }

    const groups = buildExclusiveGroups(typeInputs)

    expect(groups[0].label).toBe('unknown_field')
  })
})

describe('detectActiveGroupIndex', () => {
  const groups = [
    { fieldIds: ['oauth_token'], label: 'OAuth Token' },
    { fieldIds: ['username', 'password'], label: 'Username + Password' },
  ]

  it('returns 0 when no group has values', () => {
    expect(detectActiveGroupIndex(groups, {})).toBe(0)
  })

  it('returns 0 when first group has values', () => {
    expect(detectActiveGroupIndex(groups, { oauth_token: 'token123' })).toBe(0)
  })

  it('returns 1 when second group has values', () => {
    expect(detectActiveGroupIndex(groups, { username: 'admin', password: 'secret' })).toBe(1)
  })

  it('ignores empty string values', () => {
    expect(detectActiveGroupIndex(groups, { oauth_token: '' })).toBe(0)
  })

  it('returns first group with values when both somehow have values', () => {
    expect(detectActiveGroupIndex(groups, { oauth_token: 'token', username: 'admin' })).toBe(0)
  })
})

describe('getVisibleFields', () => {
  it('returns all fields when no mutually_exclusive groups', () => {
    const typeInputs = {
      fields: aapFields,
      required: [],
      mutually_exclusive: [],
      mutually_exclusive_labels: [],
      mutually_exclusive_help: '',
      required_one_of: [],
      required_together: [],
    }

    expect(getVisibleFields(typeInputs, 0)).toEqual(aapFields)
  })

  it('shows common fields plus active group fields for group 0', () => {
    const visible = getVisibleFields(aapTypeInputs, 0)
    const visibleIds = visible.map((f) => f.id)

    expect(visibleIds).toEqual(['oauth_token'])
  })

  it('shows common fields plus active group fields for group 1', () => {
    const visible = getVisibleFields(aapTypeInputs, 1)
    const visibleIds = visible.map((f) => f.id)

    expect(visibleIds).toEqual(['username', 'password'])
  })
})

describe('getAuthMethodInsertIndex', () => {
  it('returns -1 when no mutually_exclusive groups', () => {
    const typeInputs = {
      fields: aapFields,
      required: [],
      mutually_exclusive: [],
      mutually_exclusive_labels: [],
      mutually_exclusive_help: '',
      required_one_of: [],
      required_together: [],
    }

    expect(getAuthMethodInsertIndex(aapFields, typeInputs)).toBe(-1)
  })

  it('returns index of first exclusive field in visible fields for group 0', () => {
    const visible = getVisibleFields(aapTypeInputs, 0)

    expect(getAuthMethodInsertIndex(visible, aapTypeInputs)).toBe(0)
  })

  it('returns index of first exclusive field in visible fields for group 1', () => {
    const visible = getVisibleFields(aapTypeInputs, 1)

    expect(getAuthMethodInsertIndex(visible, aapTypeInputs)).toBe(0)
  })
})

describe('validateFieldConstraints', () => {
  it('returns true when no constraints present', () => {
    const setError = makeSetError()
    const typeInputs = {
      fields: aapFields,
      required: [],
      mutually_exclusive: [],
      mutually_exclusive_labels: [],
      mutually_exclusive_help: '',
      required_one_of: [],
      required_together: [],
    }

    expect(validateFieldConstraints(typeInputs, {}, setError)).toBe(true)
    expect(setError).not.toHaveBeenCalled()
  })

  it('returns true when required_together group is fully filled', () => {
    const setError = makeSetError()

    expect(validateFieldConstraints(aapTypeInputs, { username: 'admin', password: 'secret' }, setError)).toBe(true)
    expect(setError).not.toHaveBeenCalled()
  })

  it('returns true when required_together group is completely empty', () => {
    const setError = makeSetError()

    expect(validateFieldConstraints(aapTypeInputs, {}, setError)).toBe(true)
    expect(setError).not.toHaveBeenCalled()
  })

  it('returns false and sets error when required_together group is partially filled', () => {
    const setError = makeSetError()

    const result = validateFieldConstraints(aapTypeInputs, { username: 'admin' }, setError)

    expect(result).toBe(false)
    expect(setError).toHaveBeenCalledWith('inputs.password', { message: 'Password is required' })
  })

  it('sets error for username when only password is provided', () => {
    const setError = makeSetError()

    validateFieldConstraints(aapTypeInputs, { password: 'secret' }, setError)

    expect(setError).toHaveBeenCalledWith('inputs.username', { message: 'Username is required' })
  })
})

describe('getAllExclusiveFieldIds', () => {
  it('returns a Set of all exclusive field IDs', () => {
    const result = getAllExclusiveFieldIds(aapTypeInputs)

    expect(result).toEqual(new Set(['oauth_token', 'username', 'password']))
  })

  it('returns an empty Set when no mutually_exclusive groups', () => {
    const typeInputs = {
      fields: aapFields,
      required: [],
      mutually_exclusive: [],
      mutually_exclusive_labels: [],
      mutually_exclusive_help: '',
      required_one_of: [],
      required_together: [],
    }

    expect(getAllExclusiveFieldIds(typeInputs)).toEqual(new Set())
  })
})

describe('validateAllDynamicFields', () => {
  it('returns true when typeInputs is null', () => {
    const setError = makeSetError()

    expect(
      validateAllDynamicFields(
        { typeInputs: null, inputs: {}, visibleFields: [], isEditMode: false, touchedSecrets: new Set() },
        setError
      )
    ).toBe(true)
  })

  it('validates required fields in create mode', () => {
    const setError = makeSetError()
    const visible = getVisibleFields(aapTypeInputs, 0)

    const result = validateAllDynamicFields(
      { typeInputs: aapTypeInputs, inputs: {}, visibleFields: visible, isEditMode: false, touchedSecrets: new Set() },
      setError
    )

    expect(result).toBe(false)
    expect(setError).toHaveBeenCalledWith('inputs.oauth_token', { message: 'OAuth Token is required' })
  })

  it('skips validation for non-visible required fields', () => {
    const setError = makeSetError()
    const visible = getVisibleFields(aapTypeInputs, 0)

    validateAllDynamicFields(
      {
        typeInputs: aapTypeInputs,
        inputs: { oauth_token: 'tok' },
        visibleFields: visible,
        isEditMode: false,
        touchedSecrets: new Set(),
      },
      setError
    )

    expect(setError).not.toHaveBeenCalled()
  })

  it('validates required_one_of fields for the active group in create mode', () => {
    const setError = makeSetError()
    const visible = getVisibleFields(aapTypeInputs, 0)

    const result = validateAllDynamicFields(
      {
        typeInputs: aapTypeInputs,
        inputs: {},
        visibleFields: visible,
        isEditMode: false,
        touchedSecrets: new Set(),
      },
      setError
    )

    expect(result).toBe(false)
    expect(setError).toHaveBeenCalledWith('inputs.oauth_token', { message: 'OAuth Token is required' })
  })

  it('skips required_one_of validation for hidden groups', () => {
    const setError = makeSetError()
    const visible = getVisibleFields(aapTypeInputs, 0)

    validateAllDynamicFields(
      {
        typeInputs: aapTypeInputs,
        inputs: { oauth_token: 'tok' },
        visibleFields: visible,
        isEditMode: false,
        touchedSecrets: new Set(),
      },
      setError
    )

    expect(setError).not.toHaveBeenCalledWith('inputs.username', expect.anything())
    expect(setError).not.toHaveBeenCalledWith('inputs.password', expect.anything())
  })

  it('validates required_one_of fields for the second group when active', () => {
    const setError = makeSetError()
    const visible = getVisibleFields(aapTypeInputs, 1)

    const result = validateAllDynamicFields(
      {
        typeInputs: aapTypeInputs,
        inputs: { host: 'https://aap.example.com' },
        visibleFields: visible,
        isEditMode: false,
        touchedSecrets: new Set(),
      },
      setError
    )

    expect(result).toBe(false)
    expect(setError).toHaveBeenCalledWith('inputs.username', { message: 'Username is required' })
    expect(setError).toHaveBeenCalledWith('inputs.password', { message: 'Password is required' })
  })

  it('skips required_one_of secret fields in edit mode when untouched', () => {
    const setError = makeSetError()
    const visible = getVisibleFields(aapTypeInputs, 0)

    const result = validateAllDynamicFields(
      {
        typeInputs: aapTypeInputs,
        inputs: { host: 'https://aap.example.com' },
        visibleFields: visible,
        isEditMode: true,
        touchedSecrets: new Set(),
      },
      setError
    )

    expect(result).toBe(true)
    expect(setError).not.toHaveBeenCalled()
  })

  it('validates required_one_of secret fields in edit mode when touched and empty', () => {
    const setError = makeSetError()
    const visible = getVisibleFields(aapTypeInputs, 0)

    const result = validateAllDynamicFields(
      {
        typeInputs: aapTypeInputs,
        inputs: { host: 'https://aap.example.com', oauth_token: '' },
        visibleFields: visible,
        isEditMode: true,
        touchedSecrets: new Set(['oauth_token']),
      },
      setError
    )

    expect(result).toBe(false)
    expect(setError).toHaveBeenCalledWith('inputs.oauth_token', { message: 'OAuth Token is required' })
  })
})

describe('buildEditInputs', () => {
  it('replaces untouched secret fields with encrypted sentinel', () => {
    const result = buildEditInputs({ host: 'example.com', oauth_token: 'tok' }, aapTypeInputs, new Set())

    expect(result.host).toBe('example.com')
    expect(result.oauth_token).toBe(ENCRYPTED_SENTINEL)
  })

  it('preserves touched secret field values', () => {
    const result = buildEditInputs(
      { host: 'example.com', oauth_token: 'new-token' },
      aapTypeInputs,
      new Set(['oauth_token'])
    )

    expect(result.oauth_token).toBe('new-token')
  })

  it('returns inputs unchanged when typeInputs is null', () => {
    const inputs = { host: 'example.com' }

    expect(buildEditInputs(inputs, null, new Set())).toEqual(inputs)
  })
})

describe('stripHiddenGroupFields', () => {
  it('removes fields from hidden exclusive groups', () => {
    const visible = getVisibleFields(aapTypeInputs, 0)

    const result = stripHiddenGroupFields(
      { host: 'example.com', oauth_token: 'tok', username: 'admin', password: 'secret' },
      aapTypeInputs,
      visible
    )

    expect(result).toEqual({ host: 'example.com', oauth_token: 'tok' })
  })

  it('returns inputs unchanged when no mutually_exclusive groups', () => {
    const typeInputs = {
      fields: aapFields,
      required: [],
      mutually_exclusive: [],
      mutually_exclusive_labels: [],
      mutually_exclusive_help: '',
      required_one_of: [],
      required_together: [],
    }
    const inputs = { host: 'example.com', oauth_token: 'tok' }

    expect(stripHiddenGroupFields(inputs, typeInputs, aapFields)).toEqual(inputs)
  })

  it('returns inputs unchanged when typeInputs is null', () => {
    const inputs = { host: 'example.com' }

    expect(stripHiddenGroupFields(inputs, null, [])).toEqual(inputs)
  })
})
