import { ActivityTypeEnum } from '@syntara/contracts'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const mockAddActivity = vi.fn()
const mockBatchAddActivitiesAndEdges = vi.fn()

vi.mock('../../../../stores/useWorkflowStore', () => ({
  createConditionActivity: vi.fn((_id: string, _name: string, condition: string) => ({
    type: ActivityTypeEnum.CONDITION,
    condition,
  })),
  createConvergeActivity: vi.fn((_id: string, _name: string, parameters: unknown) => ({
    type: ActivityTypeEnum.CONVERGE,
    parameters,
  })),
  createGenericActivity: vi.fn((id: string, name: string, msg: string) => ({
    type: 'task',
    id,
    name,
    msg,
  })),
  createLoopActivity: vi.fn((_id: string, _name: string, loopType: string, opts: unknown) => ({
    type: ActivityTypeEnum.LOOP,
    loopType,
    opts,
  })),
  createSwitchActivity: vi.fn((_id: string, _name: string, cases: unknown) => ({
    type: ActivityTypeEnum.SWITCH,
    cases,
  })),
  createWaitActivity: vi.fn((_id: string, _name: string, config: unknown) => ({
    type: ActivityTypeEnum.WAIT,
    parameters: config,
  })),
  useWorkflowStore: {
    getState: vi.fn(() => ({
      addActivity: mockAddActivity,
      edges: [],
      batchAddActivitiesAndEdges: mockBatchAddActivitiesAndEdges,
    })),
  },
}))

vi.mock('../../utils/nodeNaming', () => ({
  getDefaultNodeBaseName: vi.fn(() => 'base'),
  getNodeDisplayName: vi.fn((_base: string, name?: string) => name ?? 'base'),
}))

import {
  buildLogicStepName,
  generateSecureRandomId,
  submitConditionLogic,
  submitConvergeLogic,
  submitLoopLogic,
  submitSwitchLogic,
  submitWaitLogic,
} from './registerLogicNodeSubmit'

describe('registerLogicNodeSubmit', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('generateSecureRandomId', () => {
    it('returns a non-empty id when crypto is available', () => {
      const id = generateSecureRandomId()
      expect(id.length).toBeGreaterThan(0)
    })

    it('throws when getRandomValues is unavailable', () => {
      const original = globalThis.crypto
      Object.defineProperty(globalThis, 'crypto', {
        configurable: true,
        value: { getRandomValues: undefined },
      })
      try {
        expect(() => generateSecureRandomId()).toThrow(/Cryptographically secure random/)
      } finally {
        Object.defineProperty(globalThis, 'crypto', { configurable: true, value: original })
      }
    })
  })

  describe('buildLogicStepName', () => {
    it('builds display name from form data', () => {
      expect(
        buildLogicStepName({
          logicType: ActivityTypeEnum.CONDITION,
          name: 'My Branch',
        })
      ).toBe('My Branch')
    })

    it('resolves converge label path', () => {
      expect(
        buildLogicStepName({
          logicType: ActivityTypeEnum.CONVERGE,
          name: 'Join',
        })
      ).toBe('Join')
    })

    it('resolves wait label path', () => {
      expect(
        buildLogicStepName({
          logicType: ActivityTypeEnum.WAIT,
          name: 'Pause',
        })
      ).toBe('Pause')
    })

    it('resolves loop label path', () => {
      expect(
        buildLogicStepName({
          logicType: ActivityTypeEnum.LOOP,
          name: 'Iter',
          type: 'while',
        })
      ).toBe('Iter')
    })
  })

  describe('submitConditionLogic', () => {
    it('returns true and adds activity when condition missing', () => {
      expect(submitConditionLogic('id', 'n', { logicType: ActivityTypeEnum.CONDITION, name: 'x' })).toBe(true)
      expect(mockAddActivity).toHaveBeenCalled()
    })

    it('returns true and adds activity when condition present', () => {
      expect(
        submitConditionLogic('cid', 'Cond', {
          logicType: ActivityTypeEnum.CONDITION,
          name: 'x',
          condition: 'true',
        })
      ).toBe(true)
      expect(mockAddActivity).toHaveBeenCalled()
    })
  })

  describe('submitLoopLogic', () => {
    it('rejects invalid loop type', () => {
      const onSuccess = vi.fn()
      const onError = vi.fn()
      expect(
        submitLoopLogic({
          activityId: 'l1',
          name: 'L',
          data: { logicType: ActivityTypeEnum.LOOP, name: 'L', type: 'invalid' },
          generateId: () => 'x',
          onSuccess,
          onError,
        })
      ).toBe(false)
      expect(onError).toHaveBeenCalledWith('Loop type must be forEach or while')
      expect(mockBatchAddActivitiesAndEdges).not.toHaveBeenCalled()
    })

    it('creates forEach loop even without items', () => {
      const onSuccess = vi.fn()
      expect(
        submitLoopLogic({
          activityId: 'l1',
          name: 'L',
          data: { logicType: ActivityTypeEnum.LOOP, name: 'L', type: 'forEach' },
          generateId: () => 'x',
          onSuccess,
          onError: vi.fn(),
        })
      ).toBe(true)
      expect(mockBatchAddActivitiesAndEdges).toHaveBeenCalled()
    })

    it('creates while loop even without condition', () => {
      const onSuccess = vi.fn()
      expect(
        submitLoopLogic({
          activityId: 'l1',
          name: 'L',
          data: { logicType: ActivityTypeEnum.LOOP, name: 'L', type: 'while' },
          generateId: () => 'x',
          onSuccess,
          onError: vi.fn(),
        })
      ).toBe(true)
      expect(mockBatchAddActivitiesAndEdges).toHaveBeenCalled()
    })

    it('returns true and batches activities for valid forEach loop', () => {
      const onSuccess = vi.fn()
      expect(
        submitLoopLogic({
          activityId: 'loop-1',
          name: 'Each',
          data: {
            logicType: ActivityTypeEnum.LOOP,
            name: 'Each',
            type: 'forEach',
            items: 'ctx.items',
          },
          generateId: () => 'abc',
          onSuccess,
          onError: vi.fn(),
        })
      ).toBe(true)
      expect(mockBatchAddActivitiesAndEdges).toHaveBeenCalled()
      expect(onSuccess).toHaveBeenCalledWith('loop-1')
    })

    it('returns true for valid while loop', () => {
      const onSuccess = vi.fn()
      expect(
        submitLoopLogic({
          activityId: 'loop-2',
          name: 'While',
          data: {
            logicType: ActivityTypeEnum.LOOP,
            name: 'While',
            type: 'while',
            condition: 'true',
          },
          generateId: () => 'xyz',
          onSuccess,
          onError: vi.fn(),
        })
      ).toBe(true)
      expect(mockBatchAddActivitiesAndEdges).toHaveBeenCalled()
      expect(onSuccess).toHaveBeenCalledWith('loop-2')
    })
  })

  describe('submitConvergeLogic', () => {
    it('creates activity even when strategy missing', () => {
      expect(submitConvergeLogic('c1', 'C', { logicType: ActivityTypeEnum.CONVERGE, name: 'C' })).toBe(true)
      expect(mockAddActivity).toHaveBeenCalled()
    })

    it('creates activity for strategy any even with zero requiredPathCount', () => {
      expect(
        submitConvergeLogic('c1', 'C', {
          logicType: ActivityTypeEnum.CONVERGE,
          name: 'C',
          strategy: 'any',
          requiredPathCount: 0,
        } as never)
      ).toBe(true)
      expect(mockAddActivity).toHaveBeenCalled()
    })

    it('returns true and adds activity for strategy all', () => {
      expect(
        submitConvergeLogic('c1', 'Join', {
          logicType: ActivityTypeEnum.CONVERGE,
          name: 'Join',
          strategy: 'all',
        } as never)
      ).toBe(true)
      expect(mockAddActivity).toHaveBeenCalled()
    })

    it('returns true for strategy any with required fields', () => {
      expect(
        submitConvergeLogic('c2', 'Any join', {
          logicType: ActivityTypeEnum.CONVERGE,
          name: 'Any join',
          strategy: 'any',
          requiredPathCount: 2,
          timeout: 60,
          onTimeout: 'fail',
        } as never)
      ).toBe(true)
      expect(mockAddActivity).toHaveBeenCalled()
    })
  })

  describe('submitSwitchLogic', () => {
    it('creates activity when cases are missing', () => {
      expect(submitSwitchLogic('s1', 'S', { logicType: ActivityTypeEnum.SWITCH, name: 'S' })).toBe(true)
      expect(mockAddActivity).toHaveBeenCalled()
    })

    it('creates activity when cases array is empty', () => {
      expect(submitSwitchLogic('s1', 'S', { logicType: ActivityTypeEnum.SWITCH, name: 'S', cases: [] })).toBe(true)
      expect(mockAddActivity).toHaveBeenCalled()
    })

    it('returns true and adds activity for valid cases', () => {
      expect(
        submitSwitchLogic('s1', 'Route', {
          logicType: ActivityTypeEnum.SWITCH,
          name: 'Route',
          cases: [{ caseId: 'c1', condition: '${status} == "approved"' }],
        })
      ).toBe(true)
      expect(mockAddActivity).toHaveBeenCalled()
      const activity = mockAddActivity.mock.calls[0][0] as {
        cases: Array<{ port: string; label: string; condition: string }>
      }
      expect(activity.cases[0].condition).toBe('${status} == "approved"')
      expect(activity.cases[0].port).toBe('case_0')
      expect(activity.cases[0].label).toBe('Path 1')
    })

    it('returns true for multiple cases with different conditions', () => {
      expect(
        submitSwitchLogic('s2', 'Multi Route', {
          logicType: ActivityTypeEnum.SWITCH,
          name: 'Multi Route',
          cases: [
            { caseId: 'c1', condition: '${priority} > 7' },
            { caseId: 'c2', condition: 'not(${status} == "rejected")' },
          ],
        })
      ).toBe(true)
      expect(mockAddActivity).toHaveBeenCalled()
      const activity = mockAddActivity.mock.calls[0][0] as {
        cases: Array<{ port: string; label: string; condition: string }>
      }
      expect(activity.cases).toHaveLength(2)
      expect(activity.cases[0].port).toBe('case_0')
      expect(activity.cases[1].port).toBe('case_1')
    })

    it('serializes conditions with labels using custom path names', () => {
      submitSwitchLogic('s3', 'Named Paths', {
        logicType: ActivityTypeEnum.SWITCH,
        name: 'Named Paths',
        cases: [
          { caseId: 'c1', label: 'High Priority', condition: '${priority} > 7' },
          { caseId: 'c2', label: 'Low Priority', condition: '${priority} < 3' },
        ],
      })
      expect(mockAddActivity).toHaveBeenCalled()
      const activity = mockAddActivity.mock.calls[0][0] as {
        cases: Array<{ port: string; label: string; condition: string }>
      }
      expect(activity.cases[0].label).toBe('High Priority')
      expect(activity.cases[1].label).toBe('Low Priority')
    })
  })

  describe('submitWaitLogic', () => {
    it('creates wait activity with computed duration and returns true', () => {
      const result = submitWaitLogic('w1', 'Wait 5m', {
        logicType: ActivityTypeEnum.WAIT,
        name: 'Wait 5m',
        days: 0,
        hours: 0,
        minutes: 5,
        seconds: 0,
      } as never)

      expect(result).toBe(true)
      expect(mockAddActivity).toHaveBeenCalled()
    })

    it('defaults missing time fields to 0', () => {
      const result = submitWaitLogic('w2', 'Minimal', {
        logicType: ActivityTypeEnum.WAIT,
        name: 'Minimal',
      })

      expect(result).toBe(true)
      expect(mockAddActivity).toHaveBeenCalled()
    })

    it('computes total seconds from all time units', () => {
      submitWaitLogic('w3', 'Full', {
        logicType: ActivityTypeEnum.WAIT,
        name: 'Full',
        days: 1,
        hours: 2,
        minutes: 30,
        seconds: 15,
      } as never)

      expect(mockAddActivity).toHaveBeenCalled()
    })
  })
})
