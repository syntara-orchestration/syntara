import { beforeEach, describe, expect, it, vi } from 'vitest'

const {
  mockAddActivity,
  mockBatchAddActivitiesAndEdges,
  mockCreateConditionActivity,
  mockCreateConvergeActivity,
  mockCreateGenericActivity,
  mockCreateLoopActivity,
  mockCreateWaitActivity,
  mockRegister,
} = vi.hoisted(() => ({
  mockAddActivity: vi.fn(),
  mockBatchAddActivitiesAndEdges: vi.fn(),
  mockCreateConditionActivity: vi.fn((id: string, name: string, condition: string) => ({
    type: 'condition',
    id,
    name,
    condition,
  })),
  mockCreateConvergeActivity: vi.fn((id: string, name: string, config?: Record<string, unknown>) => ({
    type: 'converge',
    id,
    name,
    config,
  })),
  mockCreateGenericActivity: vi.fn((id: string, name: string, msg?: string) => ({ type: 'task', id, name, msg })),
  mockCreateLoopActivity: vi.fn((id: string, name: string, type: string, opts?: Record<string, unknown>) => ({
    type: 'loop',
    id,
    name,
    loopType: type,
    ...opts,
  })),
  mockCreateWaitActivity: vi.fn((id: string, name: string, config: Record<string, unknown>) => ({
    type: 'wait',
    id,
    name,
    parameters: config,
  })),
  mockRegister: vi.fn(),
}))

vi.mock('../../../../stores/useWorkflowStore', () => ({
  createConditionActivity: mockCreateConditionActivity,
  createConvergeActivity: mockCreateConvergeActivity,
  createGenericActivity: mockCreateGenericActivity,
  createLoopActivity: mockCreateLoopActivity,
  createWaitActivity: mockCreateWaitActivity,
  useWorkflowStore: {
    getState: vi.fn(() => ({
      addActivity: mockAddActivity,
      edges: [],
      batchAddActivitiesAndEdges: mockBatchAddActivitiesAndEdges,
    })),
  },
}))

vi.mock('../../utils/nodeNaming', () => ({
  getDefaultNodeBaseName: vi.fn(() => 'Converge'),
  getNodeDisplayName: vi.fn((_base: unknown, name?: string) => name ?? 'Converge'),
}))

vi.mock('../helpers/nodeTemplates', () => ({
  createCustomNode: vi.fn((parameters: Record<string, unknown>, handler: (...args: unknown[]) => void) => ({
    ...parameters,
    onSubmit: handler,
  })),
}))

vi.mock('../NodeRegistry', () => ({
  NodeRegistry: { register: mockRegister },
}))

import registerLogicNode from './registerLogicNode'

function getHandler() {
  type HandlerFn = (
    data: Record<string, unknown>,
    onSuccess: (id?: string) => void,
    onError: (err: string) => void
  ) => void
  const definition = mockRegister.mock.calls[0][0] as unknown as { onSubmit: HandlerFn }
  return definition.onSubmit
}

describe('registerLogicNode', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    registerLogicNode()
  })

  it('every logic subtype has initialData with logicType', () => {
    const definition = mockRegister.mock.calls[0][0] as unknown as {
      subtypes: Array<{ id: string; initialData?: { logicType?: string } }>
    }
    for (const subtype of definition.subtypes) {
      expect(subtype.initialData?.logicType, `${subtype.id} missing initialData.logicType`).toBeDefined()
    }
  })

  describe('Converge', () => {
    it('creates activity even when strategy is missing', () => {
      const onSuccess = vi.fn()
      const onError = vi.fn()
      getHandler()({ logicType: 'converge', name: 'Test' }, onSuccess, onError)

      expect(mockCreateConvergeActivity).toHaveBeenCalled()
      expect(mockAddActivity).toHaveBeenCalled()
      expect(onSuccess).toHaveBeenCalledWith(expect.stringMatching(/^logic_\d+_[a-z0-9]+$/))
      expect(onError).not.toHaveBeenCalled()
    })

    it('calls createConvergeActivity and onSuccess for valid strategy all', () => {
      const onSuccess = vi.fn()
      const onError = vi.fn()
      getHandler()({ logicType: 'converge', name: 'Join All', strategy: 'all' }, onSuccess, onError)

      expect(mockCreateConvergeActivity).toHaveBeenCalledWith(
        expect.stringMatching(/^logic_\d+_[a-z0-9]+$/),
        'Join All',
        expect.objectContaining({ strategy: 'all' }),
        undefined
      )
      expect(mockAddActivity).toHaveBeenCalled()
      expect(onSuccess).toHaveBeenCalledWith(expect.stringMatching(/^logic_\d+_[a-z0-9]+$/))
      expect(onError).not.toHaveBeenCalled()
    })

    it('passes settings to factory when provided', () => {
      const onSuccess = vi.fn()
      const onError = vi.fn()
      getHandler()(
        {
          logicType: 'converge',
          name: 'Join',
          strategy: 'all',
          settings: { timeout: 3600, continue_on_failure: true },
        },
        onSuccess,
        onError
      )

      expect(mockCreateConvergeActivity).toHaveBeenCalledWith(
        expect.any(String),
        'Join',
        expect.objectContaining({ strategy: 'all' }),
        expect.objectContaining({ timeout: 3600, continue_on_failure: true })
      )
      expect(onSuccess).toHaveBeenCalled()
    })

    it('creates activity even when strategy any is missing requiredPathCount', () => {
      const onSuccess = vi.fn()
      const onError = vi.fn()
      getHandler()(
        {
          logicType: 'converge',
          name: 'Join Any',
          strategy: 'any',
        },
        onSuccess,
        onError
      )

      expect(mockCreateConvergeActivity).toHaveBeenCalledWith(
        expect.any(String),
        'Join Any',
        expect.objectContaining({ strategy: 'any' }),
        undefined
      )
      expect(mockAddActivity).toHaveBeenCalled()
      expect(onSuccess).toHaveBeenCalledWith(expect.stringMatching(/^logic_\d+_[a-z0-9]+$/))
      expect(onError).not.toHaveBeenCalled()
    })

    it('calls createConvergeActivity and onSuccess for strategy any with all required fields', () => {
      const onSuccess = vi.fn()
      const onError = vi.fn()
      getHandler()(
        {
          logicType: 'converge',
          name: 'Join Any',
          strategy: 'any',
          requiredPathCount: 2,
        },
        onSuccess,
        onError
      )

      expect(mockCreateConvergeActivity).toHaveBeenCalledWith(
        expect.any(String),
        'Join Any',
        expect.objectContaining({
          strategy: 'any',
          requiredPathCount: 2,
        }),
        undefined
      )
      expect(mockAddActivity).toHaveBeenCalled()
      expect(onSuccess).toHaveBeenCalled()
      expect(onError).not.toHaveBeenCalled()
    })
  })

  describe('Condition', () => {
    it('creates activity even when condition is missing', () => {
      const onSuccess = vi.fn()
      const onError = vi.fn()
      getHandler()({ logicType: 'condition', name: 'Check' }, onSuccess, onError)

      expect(mockCreateConditionActivity).toHaveBeenCalled()
      expect(mockAddActivity).toHaveBeenCalled()
      expect(onSuccess).toHaveBeenCalledWith(expect.stringMatching(/^logic_\d+_[a-z0-9]+$/))
      expect(onError).not.toHaveBeenCalled()
    })

    it('calls createConditionActivity and onSuccess for valid condition', () => {
      const onSuccess = vi.fn()
      const onError = vi.fn()
      getHandler()({ logicType: 'condition', name: 'Check', condition: 'x > 0' }, onSuccess, onError)

      expect(mockCreateConditionActivity).toHaveBeenCalledWith(
        expect.stringMatching(/^logic_\d+_[a-z0-9]+$/),
        'Check',
        'x > 0'
      )
      expect(mockAddActivity).toHaveBeenCalled()
      expect(onSuccess).toHaveBeenCalled()
      expect(onError).not.toHaveBeenCalled()
    })
  })

  describe('Loop', () => {
    it('creates activity even when forEach is missing items', () => {
      const onSuccess = vi.fn()
      const onError = vi.fn()
      getHandler()({ logicType: 'loop', type: 'forEach', name: 'Loop' }, onSuccess, onError)

      expect(mockBatchAddActivitiesAndEdges).toHaveBeenCalled()
      expect(onSuccess).toHaveBeenCalled()
      expect(onError).not.toHaveBeenCalled()
    })

    it('creates activity even when while is missing condition', () => {
      const onSuccess = vi.fn()
      const onError = vi.fn()
      getHandler()({ logicType: 'loop', type: 'while', name: 'While Loop' }, onSuccess, onError)

      expect(mockBatchAddActivitiesAndEdges).toHaveBeenCalled()
      expect(onSuccess).toHaveBeenCalled()
      expect(onError).not.toHaveBeenCalled()
    })
  })

  describe('Wait', () => {
    it('calls onSuccess for valid wait data', () => {
      const onSuccess = vi.fn()
      const onError = vi.fn()
      getHandler()(
        { logicType: 'wait', name: 'Pause 5m', days: 0, hours: 0, minutes: 5, seconds: 0 },
        onSuccess,
        onError
      )

      expect(onSuccess).toHaveBeenCalledWith(expect.stringMatching(/^logic_\d+_[a-z0-9]+$/))
      expect(onError).not.toHaveBeenCalled()
    })

    it('defaults missing time fields to zero', () => {
      const onSuccess = vi.fn()
      const onError = vi.fn()
      getHandler()({ logicType: 'wait', name: 'Quick Wait' }, onSuccess, onError)

      expect(onSuccess).toHaveBeenCalled()
      expect(onError).not.toHaveBeenCalled()
    })
  })

  describe('Loop (valid)', () => {
    it('calls onSuccess for valid forEach loop', () => {
      const onSuccess = vi.fn()
      const onError = vi.fn()
      getHandler()({ logicType: 'loop', name: 'Each Item', type: 'forEach', items: 'ctx.list' }, onSuccess, onError)

      expect(mockBatchAddActivitiesAndEdges).toHaveBeenCalled()
      expect(onSuccess).toHaveBeenCalled()
      expect(onError).not.toHaveBeenCalled()
    })

    it('calls onSuccess for valid while loop', () => {
      const onSuccess = vi.fn()
      const onError = vi.fn()
      getHandler()({ logicType: 'loop', name: 'While', type: 'while', condition: 'count < 10' }, onSuccess, onError)

      expect(mockBatchAddActivitiesAndEdges).toHaveBeenCalled()
      expect(onSuccess).toHaveBeenCalled()
      expect(onError).not.toHaveBeenCalled()
    })
  })

  describe('Invalid logicType', () => {
    it('calls onError for invalid logicType', () => {
      const onSuccess = vi.fn()
      const onError = vi.fn()
      getHandler()({ logicType: 'invalid', name: 'Bad' }, onSuccess, onError)

      expect(onError).toHaveBeenCalledWith('Invalid logic type')
      expect(onSuccess).not.toHaveBeenCalled()
    })
  })

  describe('Error handling', () => {
    it('catches thrown Error and calls onError with message', () => {
      mockAddActivity.mockImplementation(() => {
        throw new Error('Store error')
      })
      const onSuccess = vi.fn()
      const onError = vi.fn()
      getHandler()({ logicType: 'condition', name: 'Crash', condition: 'x > 0' }, onSuccess, onError)

      expect(onError).toHaveBeenCalledWith('Store error')
      expect(onSuccess).not.toHaveBeenCalled()
    })

    it('catches non-Error throw and calls onError with generic message', () => {
      mockAddActivity.mockImplementation(() => {
        // Simulate a non-Error throwable reaching the catch block
        const nonError = Object.create(null) as Error
        throw nonError
      })
      const onSuccess = vi.fn()
      const onError = vi.fn()
      getHandler()({ logicType: 'condition', name: 'Crash', condition: 'x > 0' }, onSuccess, onError)

      expect(onError).toHaveBeenCalledWith('Failed to add logic step')
      expect(onSuccess).not.toHaveBeenCalled()
    })
  })
})
