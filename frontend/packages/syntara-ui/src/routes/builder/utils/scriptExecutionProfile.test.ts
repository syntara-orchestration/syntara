import { describe, expect, it } from 'vitest'

import {
  ScriptAffinityEnum,
  buildScriptExecutionProfile,
  parseScriptExecutionFormFields,
} from './scriptExecutionProfile'

describe('scriptExecutionProfile', () => {
  describe('parseScriptExecutionFormFields', () => {
    it('defaults to none when execution_profile is missing', () => {
      expect(parseScriptExecutionFormFields({})).toEqual({ affinity: ScriptAffinityEnum.NONE })
    })

    it('defaults to none when execution_profile is null', () => {
      expect(parseScriptExecutionFormFields({ execution_profile: null })).toEqual({
        affinity: ScriptAffinityEnum.NONE,
      })
    })

    it('maps a valid execution_target profile to required_target', () => {
      expect(
        parseScriptExecutionFormFields({
          execution_profile: {
            type: 'execution_target',
            execution_target_id: 'target-1',
          },
        })
      ).toEqual({
        affinity: ScriptAffinityEnum.REQUIRED_TARGET,
        execution_target_id: 'target-1',
      })
    })

    it('defaults to none for an empty execution_target_id', () => {
      expect(
        parseScriptExecutionFormFields({
          execution_profile: {
            type: 'execution_target',
            execution_target_id: '   ',
          },
        })
      ).toEqual({ affinity: ScriptAffinityEnum.NONE })
    })
  })

  describe('buildScriptExecutionProfile', () => {
    it('returns undefined for none affinity', () => {
      expect(buildScriptExecutionProfile(ScriptAffinityEnum.NONE, 'target-1')).toBeUndefined()
    })

    it('returns undefined when affinity is undefined', () => {
      expect(buildScriptExecutionProfile(undefined, 'target-1')).toBeUndefined()
    })

    it('builds an execution_target profile for required_target', () => {
      expect(buildScriptExecutionProfile(ScriptAffinityEnum.REQUIRED_TARGET, 'target-1')).toEqual({
        type: 'execution_target',
        execution_target_id: 'target-1',
      })
    })

    it('returns undefined when required_target has no id', () => {
      expect(buildScriptExecutionProfile(ScriptAffinityEnum.REQUIRED_TARGET, '  ')).toBeUndefined()
    })
  })
})
