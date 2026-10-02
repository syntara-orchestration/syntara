import { describe, expect, it, vi } from 'vitest'

import { applyDefaultValues, isExpression, sanitizeArrayField } from './aapFormHelpers'

describe('sanitizeArrayField', () => {
  it('returns array as-is when input is already an array', () => {
    expect(sanitizeArrayField([1, 2, 3])).toEqual([1, 2, 3])
  })

  it('wraps single number in array', () => {
    expect(sanitizeArrayField(42)).toEqual([42])
  })

  it('returns empty array for null', () => {
    expect(sanitizeArrayField(null)).toEqual([])
  })

  it('returns empty array for undefined', () => {
    expect(sanitizeArrayField(undefined)).toEqual([])
  })

  it('returns empty array for string', () => {
    expect(sanitizeArrayField('invalid')).toEqual([])
  })
})

describe('isExpression', () => {
  it('returns true when value contains ${', () => {
    expect(isExpression('${workflow.variables.foo}')).toBe(true)
  })

  it('returns false when value does not contain ${', () => {
    expect(isExpression('plain text')).toBe(false)
  })

  it('returns false for undefined', () => {
    expect(isExpression(undefined)).toBe(false)
  })

  it('returns false for empty string', () => {
    expect(isExpression('')).toBe(false)
  })
})

describe('applyDefaultValues', () => {
  const mockGetValues = vi.fn()
  const mockSetValue = vi.fn()

  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('Resource defaults', () => {
    it('applies default inventory when ask flag is true and no current value', () => {
      const detail = {
        ask_inventory_on_launch: true,
        default_inventory: { id: 1, name: 'Default Inventory' },
      }
      mockGetValues.mockReturnValue(undefined)

      applyDefaultValues(detail as never, false, mockGetValues as never, mockSetValue as never)

      expect(mockSetValue).toHaveBeenCalledWith('inventory_name', 'Default Inventory')
      expect(mockSetValue).toHaveBeenCalledWith('inventory_id', 1)
    })

    it('applies default inventory when template changed', () => {
      const detail = {
        ask_inventory_on_launch: true,
        default_inventory: { id: 1, name: 'Default Inventory' },
      }
      mockGetValues.mockReturnValue('Old Inventory')

      applyDefaultValues(detail as never, true, mockGetValues as never, mockSetValue as never)

      expect(mockSetValue).toHaveBeenCalledWith('inventory_name', 'Default Inventory')
      expect(mockSetValue).toHaveBeenCalledWith('inventory_id', 1)
    })

    it('does not apply inventory when ask flag is false', () => {
      const detail = {
        ask_inventory_on_launch: false,
        default_inventory: { id: 1, name: 'Default Inventory' },
      }
      mockGetValues.mockReturnValue(undefined)

      applyDefaultValues(detail as never, false, mockGetValues as never, mockSetValue as never)

      expect(mockSetValue).not.toHaveBeenCalledWith('inventory_name', expect.anything())
    })

    it('applies default execution environment', () => {
      const detail = {
        ask_execution_environment_on_launch: true,
        default_execution_environment: { id: 2, name: 'Default EE' },
      }
      mockGetValues.mockReturnValue(undefined)

      applyDefaultValues(detail as never, false, mockGetValues as never, mockSetValue as never)

      expect(mockSetValue).toHaveBeenCalledWith('execution_environment', 'Default EE')
      expect(mockSetValue).toHaveBeenCalledWith('execution_environment_id', 2)
    })

    it('applies default credentials', () => {
      const detail = {
        ask_credential_on_launch: true,
        default_credentials: [
          { id: 1, name: 'Cred 1' },
          { id: 2, name: 'Cred 2' },
        ],
      }
      mockGetValues.mockReturnValue(undefined)

      applyDefaultValues(detail as never, false, mockGetValues as never, mockSetValue as never)

      expect(mockSetValue).toHaveBeenCalledWith('job_credentials', [1, 2])
    })
  })

  describe('Scalar defaults', () => {
    it('applies default job_type', () => {
      const detail = {
        ask_job_type_on_launch: true,
        job_type: 'check',
      }
      mockGetValues.mockReturnValue(undefined)

      applyDefaultValues(detail as never, false, mockGetValues as never, mockSetValue as never)

      expect(mockSetValue).toHaveBeenCalledWith('job_type', 'check')
    })

    it('applies default verbosity with string transform', () => {
      const detail = {
        ask_verbosity_on_launch: true,
        verbosity: 2,
      }
      mockGetValues.mockReturnValue(undefined)

      applyDefaultValues(detail as never, false, mockGetValues as never, mockSetValue as never)

      expect(mockSetValue).toHaveBeenCalledWith('verbosity', '2')
    })

    it('preserves false as valid user selection', () => {
      const detail = {
        ask_diff_mode_on_launch: true,
        diff_mode: true, // Default is true
      }
      mockGetValues.mockReturnValue(false) // User explicitly set to false

      applyDefaultValues(detail as never, false, mockGetValues as never, mockSetValue as never)

      // Should NOT override the user's false selection
      expect(mockSetValue).not.toHaveBeenCalledWith('diff_mode', true)
    })

    it('preserves 0 as valid user selection for forks', () => {
      const detail = {
        ask_forks_on_launch: true,
        forks: 10, // Default is 10
      }
      mockGetValues.mockReturnValue(0) // User explicitly set to 0

      applyDefaultValues(detail as never, false, mockGetValues as never, mockSetValue as never)

      // Should NOT override the user's 0 selection
      expect(mockSetValue).not.toHaveBeenCalledWith('forks', 10)
    })

    it('treats empty string as not set for limit field', () => {
      const detail = {
        ask_limit_on_launch: true,
        limit: 'default_limit',
      }
      mockGetValues.mockReturnValue('')

      applyDefaultValues(detail as never, false, mockGetValues as never, mockSetValue as never)

      expect(mockSetValue).toHaveBeenCalledWith('limit', 'default_limit')
    })

    it('applies multiple scalar defaults', () => {
      const detail = {
        ask_forks_on_launch: true,
        forks: 5,
        ask_job_slice_count_on_launch: true,
        job_slice_count: 2,
      }
      mockGetValues.mockReturnValue(undefined)

      applyDefaultValues(detail as never, false, mockGetValues as never, mockSetValue as never)

      expect(mockSetValue).toHaveBeenCalledWith('forks', 5)
      expect(mockSetValue).toHaveBeenCalledWith('job_slice_count', 2)
    })
  })

  describe('Extra vars defaults', () => {
    it('parses YAML extra_vars and formats as JSON', () => {
      const detail = {
        ask_variables_on_launch: true,
        extra_vars: 'foo: bar\nbaz: 42',
      }
      mockGetValues.mockReturnValue(undefined)

      applyDefaultValues(detail as never, false, mockGetValues as never, mockSetValue as never)

      expect(mockSetValue).toHaveBeenCalledWith('extra_vars', expect.stringContaining('"foo": "bar"'))
      expect(mockSetValue).toHaveBeenCalledWith('extra_vars', expect.stringContaining('"baz": 42'))
    })

    it('preserves extra_vars as-is when YAML parsing fails', () => {
      const detail = {
        ask_variables_on_launch: true,
        extra_vars: 'invalid: yaml: syntax:',
      }
      mockGetValues.mockReturnValue(undefined)

      applyDefaultValues(detail as never, false, mockGetValues as never, mockSetValue as never)

      expect(mockSetValue).toHaveBeenCalledWith('extra_vars', 'invalid: yaml: syntax:')
    })

    it('does not apply extra_vars when ask flag is false', () => {
      const detail = {
        ask_variables_on_launch: false,
        extra_vars: 'foo: bar',
      }
      mockGetValues.mockReturnValue(undefined)

      applyDefaultValues(detail as never, false, mockGetValues as never, mockSetValue as never)

      expect(mockSetValue).not.toHaveBeenCalledWith('extra_vars', expect.anything())
    })

    it('does not apply extra_vars when current value exists and template not changed', () => {
      const detail = {
        ask_variables_on_launch: true,
        extra_vars: 'foo: bar',
      }
      mockGetValues.mockReturnValue('existing: value')

      applyDefaultValues(detail as never, false, mockGetValues as never, mockSetValue as never)

      expect(mockSetValue).not.toHaveBeenCalledWith('extra_vars', expect.anything())
    })

    it('overrides extra_vars when template changed even if value exists', () => {
      const detail = {
        ask_variables_on_launch: true,
        extra_vars: 'new: value',
      }
      mockGetValues.mockReturnValue('existing: value')

      applyDefaultValues(detail as never, true, mockGetValues as never, mockSetValue as never)

      expect(mockSetValue).toHaveBeenCalledWith('extra_vars', expect.stringContaining('"new": "value"'))
    })
  })

  describe('Labels defaults', () => {
    it('applies default labels when ask flag is true and no current value', () => {
      const detail = {
        ask_labels_on_launch: true,
        default_labels: [
          { id: 1, name: 'prod' },
          { id: 2, name: 'urgent' },
        ],
      }
      mockGetValues.mockReturnValue(undefined)

      applyDefaultValues(detail as never, false, mockGetValues as never, mockSetValue as never)

      expect(mockSetValue).toHaveBeenCalledWith('labels', ['prod', 'urgent'])
    })

    it('clears labels when template changed and no defaults', () => {
      const detail = {
        ask_labels_on_launch: true,
        default_labels: [],
      }
      mockGetValues.mockReturnValue(['old', 'labels'])

      applyDefaultValues(detail as never, true, mockGetValues as never, mockSetValue as never)

      expect(mockSetValue).toHaveBeenCalledWith('labels', [])
    })

    it('does not apply labels when ask flag is false', () => {
      const detail = {
        ask_labels_on_launch: false,
        default_labels: [{ id: 1, name: 'prod' }],
      }
      mockGetValues.mockReturnValue(undefined)

      applyDefaultValues(detail as never, false, mockGetValues as never, mockSetValue as never)

      expect(mockSetValue).not.toHaveBeenCalledWith('labels', expect.anything())
    })

    it('preserves user-selected labels when template not changed', () => {
      const detail = {
        ask_labels_on_launch: true,
        default_labels: [{ id: 1, name: 'prod' }],
      }
      mockGetValues.mockReturnValue(['custom', 'labels'])

      applyDefaultValues(detail as never, false, mockGetValues as never, mockSetValue as never)

      expect(mockSetValue).not.toHaveBeenCalledWith('labels', ['prod'])
    })
  })
})
