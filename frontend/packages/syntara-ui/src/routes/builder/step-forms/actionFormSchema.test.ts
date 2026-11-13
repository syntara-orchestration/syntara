import { ExecutorTypeEnum } from '@syntara/contracts'
import { describe, expect, it } from 'vitest'

import { ScriptAffinityEnum } from '../utils/scriptExecutionProfile'

import { actionFormSchema } from './actionFormSchema'

const validScriptBase = {
  executor: ExecutorTypeEnum.SCRIPT,
  name: 'My Script',
  language: 'python',
  code: 'print("hi")',
}

describe('actionFormSchema', () => {
  describe('execution_target_id', () => {
    it('accepts a valid UUID when affinity is required_target', () => {
      const result = actionFormSchema.safeParse({
        ...validScriptBase,
        affinity: ScriptAffinityEnum.REQUIRED_TARGET,
        execution_target_id: '550e8400-e29b-41d4-a716-446655440000',
      })

      expect(result.success).toBe(true)
    })

    it('rejects a non-UUID execution_target_id with the format error message', () => {
      const result = actionFormSchema.safeParse({
        ...validScriptBase,
        affinity: ScriptAffinityEnum.REQUIRED_TARGET,
        execution_target_id: 'not-a-uuid',
      })

      expect(result.success).toBe(false)
      if (result.success) return
      expect(result.error.issues).toEqual(
        expect.arrayContaining([
          expect.objectContaining({
            path: ['execution_target_id'],
            message: 'Select a valid execution target',
          }),
        ])
      )
    })

    it('requires execution_target_id when affinity is required_target', () => {
      const result = actionFormSchema.safeParse({
        ...validScriptBase,
        affinity: ScriptAffinityEnum.REQUIRED_TARGET,
      })

      expect(result.success).toBe(false)
      if (result.success) return
      expect(result.error.issues).toEqual(
        expect.arrayContaining([
          expect.objectContaining({
            path: ['execution_target_id'],
            message: 'Execution target is required',
          }),
        ])
      )
    })

    it('allows omitting execution_target_id when affinity is none', () => {
      const result = actionFormSchema.safeParse({
        ...validScriptBase,
        affinity: ScriptAffinityEnum.NONE,
      })

      expect(result.success).toBe(true)
    })
  })
})
