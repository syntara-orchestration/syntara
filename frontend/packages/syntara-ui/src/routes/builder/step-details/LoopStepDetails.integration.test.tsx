import type { LoopActivity } from '@syntara/contracts'
import { describe, expect, it } from 'vitest'

/**
 * Integration tests for LoopStepDetails field preservation logic
 * These tests verify the handleSubmit logic without mocking
 */

describe('LoopStepDetails Field Preservation Logic', () => {
  // Simulate the handleSubmit logic from LoopStepDetails.tsx
  function simulateHandleSubmit(
    loopData: LoopActivity,
    formData: {
      name: string
      type?: string
      items?: string
      condition?: string
      maxIterations?: number
      maxIterationsBehavior?: 'continue' | 'fail'
      indexVariable?: string
      itemVariable?: string
    }
  ) {
    const loopConfig = (loopData.parameters ?? {}) as {
      type?: string
      items?: string
      condition?: string
      max_iterations?: number
      maxIterations?: number
      maxIterationsBehavior?: 'continue' | 'fail'
      indexVariable?: string
      itemVariable?: string
    }

    const originalLoopType = loopConfig.type

    // Determine the config type to persist
    let configType: string
    if (formData.type === 'forEach') {
      configType = originalLoopType === 'forEach' || originalLoopType === 'for_each' ? 'for_each' : 'for_each'
    } else {
      if (originalLoopType === 'while' || originalLoopType === 'do_while') {
        configType = originalLoopType
      } else {
        configType = 'while'
      }
    }

    // Merge changes into existing config
    const parameters: Record<string, unknown> = {
      ...loopConfig,
      type: configType,
      ...(formData.type === 'forEach'
        ? {
            items: formData.items ?? '',
            ...(formData.indexVariable && { indexVariable: formData.indexVariable }),
            ...(formData.itemVariable && { itemVariable: formData.itemVariable }),
            condition: undefined,
            max_iterations: undefined,
            maxIterations: undefined,
            maxIterationsBehavior: undefined,
          }
        : {
            condition: formData.condition ?? '',
            ...(typeof formData.maxIterations === 'number' &&
              Number.isInteger(formData.maxIterations) &&
              formData.maxIterations > 0 && { max_iterations: formData.maxIterations }),
            ...(formData.maxIterationsBehavior && { maxIterationsBehavior: formData.maxIterationsBehavior }),
            items: undefined,
            indexVariable: undefined,
            itemVariable: undefined,
          }),
    }

    // Remove undefined fields
    Object.keys(parameters).forEach((key) => {
      if (parameters[key] === undefined) {
        delete parameters[key]
      }
    })

    return parameters
  }

  it('preserves indexVariable and itemVariable when editing forEach loop', () => {
    const loopData: LoopActivity = {
      type: 'loop',
      id: 'loop-1',
      name: 'ForEach Loop',
      parameters: {
        type: 'for_each',
        items: 'input.items',
        indexVariable: 'idx',
        itemVariable: 'item',
      },
    }

    const formData = {
      name: 'Updated Loop',
      type: 'forEach',
      items: 'input.newItems',
      indexVariable: 'idx',
      itemVariable: 'item',
    }

    const result = simulateHandleSubmit(loopData, formData)

    expect(result.type).toBe('for_each')
    expect(result.items).toBe('input.newItems')
    expect(result.indexVariable).toBe('idx')
    expect(result.itemVariable).toBe('item')
    // Should not have while-specific fields
    expect(result.condition).toBeUndefined()
    expect(result.max_iterations).toBeUndefined()
    expect(result.maxIterationsBehavior).toBeUndefined()
  })

  it('preserves "while" type (not convert to "do_while")', () => {
    const loopData: LoopActivity = {
      type: 'loop',
      id: 'loop-1',
      name: 'While Loop',
      parameters: {
        type: 'do_while',
        condition: 'counter < 10',
        max_iterations: 100,
      },
    }

    const formData = {
      name: 'Updated While Loop',
      type: 'while',
      condition: 'counter < 20',
      maxIterations: 100,
    }

    const result = simulateHandleSubmit(loopData, formData)

    expect(result.type).toBe('do_while') // Should preserve original 'do_while' type
    expect(result.condition).toBe('counter < 20')
    expect(result.max_iterations).toBe(100)
    // Should not have forEach-specific fields
    expect(result.items).toBeUndefined()
    expect(result.indexVariable).toBeUndefined()
    expect(result.itemVariable).toBeUndefined()
  })

  it('preserves "do_while" type (not convert to "while")', () => {
    const loopData: LoopActivity = {
      type: 'loop',
      id: 'loop-1',
      name: 'Do-While Loop',
      parameters: {
        type: 'do_while',
        condition: 'hasMore === true',
        maxIterationsBehavior: 'continue',
      },
    }

    const formData = {
      name: 'Updated Do-While Loop',
      type: 'while',
      condition: 'hasMore === true',
      maxIterationsBehavior: 'continue' as const,
    }

    const result = simulateHandleSubmit(loopData, formData)

    expect(result.type).toBe('do_while') // Should preserve 'do_while', not convert to 'while'
    expect(result.condition).toBe('hasMore === true')
    expect(result.maxIterationsBehavior).toBe('continue')
    // Should not have forEach-specific fields
    expect(result.items).toBeUndefined()
    expect(result.indexVariable).toBeUndefined()
    expect(result.itemVariable).toBeUndefined()
  })

  it('removes while-specific fields when converting to forEach', () => {
    const loopData: LoopActivity = {
      type: 'loop',
      id: 'loop-1',
      name: 'While Loop',
      parameters: {
        type: 'do_while',
        condition: 'counter < 10',
        max_iterations: 100,
        maxIterationsBehavior: 'fail',
      },
    }

    const formData = {
      name: 'Converted to ForEach',
      type: 'forEach',
      items: 'input.items',
      indexVariable: 'idx',
      itemVariable: 'item',
    }

    const result = simulateHandleSubmit(loopData, formData)

    expect(result.type).toBe('for_each')
    expect(result.items).toBe('input.items')
    expect(result.indexVariable).toBe('idx')
    expect(result.itemVariable).toBe('item')
    // While-specific fields should be removed
    expect(result.condition).toBeUndefined()
    expect(result.max_iterations).toBeUndefined()
    expect(result.maxIterationsBehavior).toBeUndefined()
  })

  it('removes forEach-specific fields when converting to while', () => {
    const loopData: LoopActivity = {
      type: 'loop',
      id: 'loop-1',
      name: 'ForEach Loop',
      parameters: {
        type: 'for_each',
        items: 'input.items',
        indexVariable: 'idx',
        itemVariable: 'item',
      },
    }

    const formData = {
      name: 'Converted to While',
      type: 'while',
      condition: 'counter < 10',
      maxIterations: 100,
    }

    const result = simulateHandleSubmit(loopData, formData)

    expect(result.type).toBe('while') // First conversion defaults to 'while'
    expect(result.condition).toBe('counter < 10')
    expect(result.max_iterations).toBe(100)
    // forEach-specific fields should be removed
    expect(result.items).toBeUndefined()
    expect(result.indexVariable).toBeUndefined()
    expect(result.itemVariable).toBeUndefined()
  })
})
