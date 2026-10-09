import { describe, expect, it } from 'vitest'

import { conditionValidationRules } from './conditionValidation'

describe('conditionValidationRules', () => {
  it('exports validation rules object', () => {
    expect(conditionValidationRules).toBeDefined()
    expect(conditionValidationRules.required).toBe('Condition is required')
    expect(typeof conditionValidationRules.validate).toBe('function')
  })

  it('validates empty condition', () => {
    const result = conditionValidationRules.validate('')
    expect(result).toBe('Condition cannot be empty')
  })

  it('accepts simple template reference', () => {
    const result = conditionValidationRules.validate('${test}')
    expect(result).toBe(true)
  })

  it('validates undefined condition', () => {
    const result = conditionValidationRules.validate(undefined)
    expect(result).toBe('Condition cannot be empty')
  })

  it('accepts valid simple condition', () => {
    const result = conditionValidationRules.validate('${true}')
    expect(result).toBe(true)
  })

  describe('Literal form validation', () => {
    it('accepts simple boolean variable', () => {
      const result = conditionValidationRules.validate('${running}')
      expect(result).toBe(true)
    })

    it('accepts property access', () => {
      const result = conditionValidationRules.validate('${user.isActive}')
      expect(result).toBe(true)
    })

    it('accepts boolean literals', () => {
      expect(conditionValidationRules.validate('${true}')).toBe(true)
      expect(conditionValidationRules.validate('${false}')).toBe(true)
    })

    it('accepts number literals', () => {
      expect(conditionValidationRules.validate('${123}')).toBe(true)
      expect(conditionValidationRules.validate('${0}')).toBe(true)
    })

    it('rejects empty template', () => {
      // Empty template ${} is invalid - has no resolvable variable
      const result = conditionValidationRules.validate('${}')
      expect(result).toBe('Please fill in all required fields (Field and Value for each condition)')
    })

    it('rejects expression with trailing comparison operator', () => {
      const result = conditionValidationRules.validate('${a} >')
      expect(result).toBe('Please fill in all required fields (Field and Value for each condition)')
    })

    it('rejects expression with trailing equals operator', () => {
      const result = conditionValidationRules.validate('${foo} ==')
      expect(result).toBe('Please fill in all required fields (Field and Value for each condition)')
    })

    it('rejects expression with trailing >=', () => {
      const result = conditionValidationRules.validate('${identifier} >=')
      expect(result).toBe('Please fill in all required fields (Field and Value for each condition)')
    })

    it('rejects expression with trailing word operator', () => {
      const result = conditionValidationRules.validate('${name} contains')
      expect(result).toBe('Please fill in all required fields (Field and Value for each condition)')
    })

    it('rejects expression with leading operator', () => {
      const result = conditionValidationRules.validate('> 5}')
      expect(result).toBe('Please fill in all required fields (Field and Value for each condition)')
    })

    it('rejects expression with leading equals', () => {
      const result = conditionValidationRules.validate('== value}')
      expect(result).toBe('Please fill in all required fields (Field and Value for each condition)')
    })

    it('rejects expression with logical AND operator', () => {
      const result = conditionValidationRules.validate('a && b')
      expect(result).toBe('Please fill in all required fields (Field and Value for each condition)')
    })

    it('rejects expression with logical OR operator', () => {
      const result = conditionValidationRules.validate('a || b')
      expect(result).toBe('Please fill in all required fields (Field and Value for each condition)')
    })

    it('rejects expression with NOT operator', () => {
      const result = conditionValidationRules.validate('!value')
      expect(result).toBe('Please fill in all required fields (Field and Value for each condition)')
    })

    it('rejects expression with parentheses', () => {
      const result = conditionValidationRules.validate('(a)')
      expect(result).toBe('Please fill in all required fields (Field and Value for each condition)')
    })

    it('rejects Python-style "and" operator', () => {
      const result = conditionValidationRules.validate('a and b')
      expect(result).toBe('Please fill in all required fields (Field and Value for each condition)')
    })

    it('rejects Python-style "or" operator', () => {
      const result = conditionValidationRules.validate('a or b')
      expect(result).toBe('Please fill in all required fields (Field and Value for each condition)')
    })

    it('rejects Python-style "not" operator', () => {
      const result = conditionValidationRules.validate('not a')
      expect(result).toBe('Please fill in all required fields (Field and Value for each condition)')
    })
  })

  describe('Parsed expression validation', () => {
    it('accepts valid comparison that parses successfully', () => {
      // This should parse into a condition node and pass validation
      const result = conditionValidationRules.validate('${trigger.age} >= 18')
      expect(result).toBe(true)
    })

    it('accepts valid string comparison', () => {
      const result = conditionValidationRules.validate('${name} == "admin"')
      expect(result).toBe(true)
    })

    it('rejects parsed expression with empty variable field', () => {
      // This would parse but have validation errors (empty variable)
      // Note: The parser might not create this structure, but if it does, validation should catch it
      const result = conditionValidationRules.validate('== value}')
      expect(result).toBe('Please fill in all required fields (Field and Value for each condition)')
    })
  })

  describe('Unary operator with value validation', () => {
    it('rejects exists operator with value', () => {
      const result = conditionValidationRules.validate('${user.email} exists foo')
      expect(result).toBe('Operators "exists" and "isEmpty" do not take a value. Remove the value after the operator.')
    })

    it('rejects isEmpty operator with value', () => {
      const result = conditionValidationRules.validate('${data} isEmpty bar')
      expect(result).toBe('Operators "exists" and "isEmpty" do not take a value. Remove the value after the operator.')
    })

    it('accepts valid exists operator without value', () => {
      const result = conditionValidationRules.validate('${user.email} exists')
      expect(result).toBe(true)
    })

    it('accepts valid isEmpty operator without value', () => {
      const result = conditionValidationRules.validate('${data} isEmpty')
      expect(result).toBe(true)
    })
  })
})
