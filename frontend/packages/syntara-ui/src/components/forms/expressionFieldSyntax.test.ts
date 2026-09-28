import { describe, expect, it } from 'vitest'

import { validateExpressionSyntax } from './expressionFieldSyntax'

describe('validateExpressionSyntax', () => {
  it('returns null for plain text without expressions', () => {
    expect(validateExpressionSyntax('hello')).toBeNull()
  })

  it('returns null for balanced expression syntax', () => {
    expect(validateExpressionSyntax('prefix ${node.output["key"]} suffix')).toBeNull()
  })

  it('flags empty expression braces', () => {
    expect(validateExpressionSyntax('value ${}')).toBe('Invalid syntax')
  })

  it('flags unbalanced brackets inside an expression', () => {
    expect(validateExpressionSyntax('${node.output["key"}')).toBe('Invalid syntax')
  })

  it('flags unclosed expression markers', () => {
    expect(validateExpressionSyntax('before ${node.output')).toBe('Invalid syntax')
  })
})
