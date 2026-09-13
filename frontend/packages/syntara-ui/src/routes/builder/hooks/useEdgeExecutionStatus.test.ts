import { TriggerTypeEnum } from '@syntara/contracts'
import { renderHook } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { useEdgeExecutionStatus } from './useEdgeExecutionStatus'

const mockDetermineEdgeStatus = vi.fn().mockReturnValue(undefined)

vi.mock('./useBuilderFlowGraph', () => ({
  executionStateEnricher: {
    determineEdgeStatus: (...args: unknown[]) => mockDetermineEdgeStatus(...args) as unknown,
  },
}))

vi.mock('../../../utils/triggerNodeIds', () => ({
  buildTriggerNodeId: (i: number) => `trigger-display-${i}`,
}))

type TestEdge = {
  id: string
  source: string
  target: string
  data: { executionStatus?: string }
}

function makeEdge(id: string, executionStatus?: string): TestEdge {
  return {
    id,
    source: 'a',
    target: 'b',
    data: executionStatus !== undefined ? { executionStatus } : {},
  }
}

const emptyWorkflow = null
const defaultActivity = new Map<string, never>()

beforeEach(() => {
  vi.clearAllMocks()
})

describe('useEdgeExecutionStatus', () => {
  describe('when isInitialized is false', () => {
    it('does not call setEdges when not initialized', () => {
      const setEdges = vi.fn()
      renderHook(() =>
        useEdgeExecutionStatus({
          effectiveExecutionStatus: 'running',
          isInitialized: false,
          currentWorkflow: emptyWorkflow,
          activityStates: defaultActivity,
          storedEdges: [],
          setEdges,
        })
      )
      expect(setEdges).not.toHaveBeenCalled()
    })

    it('does not clear edge statuses when not initialized even on truthy→null transition', () => {
      const setEdges = vi.fn()
      type StatusProps = { status: string | null }
      const initialProps: StatusProps = { status: 'running' }
      const { rerender } = renderHook(
        ({ status }: StatusProps) =>
          useEdgeExecutionStatus({
            effectiveExecutionStatus: status,
            isInitialized: false,
            currentWorkflow: emptyWorkflow,
            activityStates: defaultActivity,
            storedEdges: [],
            setEdges,
          }),
        { initialProps }
      )
      rerender({ status: null })
      expect(setEdges).not.toHaveBeenCalled()
    })
  })

  describe('cleanup: truthy → null transition', () => {
    it('clears executionStatus from edges when execution ends', () => {
      const setEdges = vi.fn()
      const edgeWithStatus = makeEdge('e1', 'running')
      type StatusProps = { status: string | null }
      const initialProps: StatusProps = { status: 'running' }

      const { rerender } = renderHook(
        ({ status }: StatusProps) =>
          useEdgeExecutionStatus({
            effectiveExecutionStatus: status,
            isInitialized: true,
            currentWorkflow: emptyWorkflow,
            activityStates: defaultActivity,
            storedEdges: [],
            setEdges,
          }),
        { initialProps }
      )

      setEdges.mockClear()
      rerender({ status: null })

      expect(setEdges).toHaveBeenCalledTimes(1)
      const updater = setEdges.mock.calls[0][0] as (edges: TestEdge[]) => TestEdge[]
      const result = updater([edgeWithStatus])
      expect(result[0].data.executionStatus).toBeUndefined()
    })

    it('returns the same edges reference when none have executionStatus (no-op)', () => {
      const setEdges = vi.fn()
      const cleanEdge = makeEdge('e1')
      type StatusProps = { status: string | null }
      const initialProps: StatusProps = { status: 'running' }

      const { rerender } = renderHook(
        ({ status }: StatusProps) =>
          useEdgeExecutionStatus({
            effectiveExecutionStatus: status,
            isInitialized: true,
            currentWorkflow: emptyWorkflow,
            activityStates: defaultActivity,
            storedEdges: [],
            setEdges,
          }),
        { initialProps }
      )

      setEdges.mockClear()
      rerender({ status: null })

      const updater = setEdges.mock.calls[0][0] as (edges: TestEdge[]) => TestEdge[]
      const input = [cleanEdge]
      const result = updater(input)
      expect(result).toBe(input)
    })

    it('does not clear edges on null → null (no transition)', () => {
      const setEdges = vi.fn()
      renderHook(() =>
        useEdgeExecutionStatus({
          effectiveExecutionStatus: null,
          isInitialized: true,
          currentWorkflow: emptyWorkflow,
          activityStates: defaultActivity,
          storedEdges: [],
          setEdges,
        })
      )
      expect(setEdges).not.toHaveBeenCalled()
    })
  })

  describe('triggerDisplayToRealId map construction', () => {
    it('builds display→real id map from workflow triggers and passes it to determineEdgeStatus', () => {
      const setEdges = vi.fn()
      const edge = makeEdge('e1')

      const workflow = {
        triggers: [
          { id: 'real-trigger-1', type: TriggerTypeEnum.MANUAL_TRIGGER, name: 'T1', parameters: {} },
          { id: 'real-trigger-2', type: TriggerTypeEnum.SCHEDULED, name: 'T2', parameters: {} },
        ],
        workflow: { activities: [] },
      } as never

      renderHook(() =>
        useEdgeExecutionStatus({
          effectiveExecutionStatus: 'running',
          isInitialized: true,
          currentWorkflow: workflow,
          activityStates: defaultActivity,
          storedEdges: [],
          setEdges,
        })
      )

      expect(setEdges).toHaveBeenCalledTimes(1)
      const updater = setEdges.mock.calls[0][0] as (edges: TestEdge[]) => TestEdge[]
      updater([edge])

      expect(mockDetermineEdgeStatus).toHaveBeenCalledWith(
        edge,
        defaultActivity,
        [],
        new Map([
          ['trigger-display-0', 'real-trigger-1'],
          ['trigger-display-1', 'real-trigger-2'],
        ]),
        []
      )
    })
  })

  describe('enrichment: active execution', () => {
    it('updates edge executionStatus when determineEdgeStatus returns a new value', () => {
      mockDetermineEdgeStatus.mockReturnValue('running')
      const setEdges = vi.fn()
      const edge = makeEdge('e1')

      renderHook(() =>
        useEdgeExecutionStatus({
          effectiveExecutionStatus: 'running',
          isInitialized: true,
          currentWorkflow: emptyWorkflow,
          activityStates: defaultActivity,
          storedEdges: [],
          setEdges,
        })
      )

      const updater = setEdges.mock.calls[0][0] as (edges: TestEdge[]) => TestEdge[]
      const result = updater([edge])
      expect(result[0].data.executionStatus).toBe('running')
    })

    it('returns the same edge reference when executionStatus is unchanged', () => {
      mockDetermineEdgeStatus.mockReturnValue('running')
      const setEdges = vi.fn()
      const edge = makeEdge('e1', 'running')

      renderHook(() =>
        useEdgeExecutionStatus({
          effectiveExecutionStatus: 'running',
          isInitialized: true,
          currentWorkflow: emptyWorkflow,
          activityStates: defaultActivity,
          storedEdges: [],
          setEdges,
        })
      )

      const updater = setEdges.mock.calls[0][0] as (edges: TestEdge[]) => TestEdge[]
      const result = updater([edge])
      expect(result[0]).toBe(edge)
    })
  })

  describe('active → terminal transitions', () => {
    it('clears edge statuses when transitioning from running to completed', () => {
      const setEdges = vi.fn()
      const edgeWithStatus = makeEdge('e1', 'running')

      const { rerender } = renderHook(
        ({ status }: { status: string | null }) =>
          useEdgeExecutionStatus({
            effectiveExecutionStatus: status,
            isInitialized: true,
            currentWorkflow: emptyWorkflow,
            activityStates: defaultActivity,
            storedEdges: [],
            setEdges,
          }),
        { initialProps: { status: 'running' } }
      )

      setEdges.mockClear()
      rerender({ status: 'completed' })

      expect(setEdges).toHaveBeenCalledTimes(1)
      const updater = setEdges.mock.calls[0][0] as (edges: TestEdge[]) => TestEdge[]
      const result = updater([edgeWithStatus])
      expect(result[0].data.executionStatus).toBeUndefined()
    })

    it('clears edge statuses when transitioning from running to failed', () => {
      const setEdges = vi.fn()
      const edgeWithStatus = makeEdge('e1', 'running')

      const { rerender } = renderHook(
        ({ status }: { status: string | null }) =>
          useEdgeExecutionStatus({
            effectiveExecutionStatus: status,
            isInitialized: true,
            currentWorkflow: emptyWorkflow,
            activityStates: defaultActivity,
            storedEdges: [],
            setEdges,
          }),
        { initialProps: { status: 'running' } }
      )

      setEdges.mockClear()
      rerender({ status: 'failed' })

      expect(setEdges).toHaveBeenCalledTimes(1)
      const updater = setEdges.mock.calls[0][0] as (edges: TestEdge[]) => TestEdge[]
      const result = updater([edgeWithStatus])
      expect(result[0].data.executionStatus).toBeUndefined()
    })

    it('clears edge statuses when transitioning from running to cancelled', () => {
      const setEdges = vi.fn()
      const edgeWithStatus = makeEdge('e1', 'running')

      const { rerender } = renderHook(
        ({ status }: { status: string | null }) =>
          useEdgeExecutionStatus({
            effectiveExecutionStatus: status,
            isInitialized: true,
            currentWorkflow: emptyWorkflow,
            activityStates: defaultActivity,
            storedEdges: [],
            setEdges,
          }),
        { initialProps: { status: 'running' } }
      )

      setEdges.mockClear()
      rerender({ status: 'cancelled' })

      expect(setEdges).toHaveBeenCalledTimes(1)
      const updater = setEdges.mock.calls[0][0] as (edges: TestEdge[]) => TestEdge[]
      const result = updater([edgeWithStatus])
      expect(result[0].data.executionStatus).toBeUndefined()
    })

    it('does not clear edge statuses during active → active transitions (running → paused)', () => {
      mockDetermineEdgeStatus.mockReturnValue('running')
      const setEdges = vi.fn()
      const edgeWithStatus = makeEdge('e1', 'running')

      const { rerender } = renderHook(
        ({ status }: { status: string | null }) =>
          useEdgeExecutionStatus({
            effectiveExecutionStatus: status,
            isInitialized: true,
            currentWorkflow: emptyWorkflow,
            activityStates: defaultActivity,
            storedEdges: [],
            setEdges,
          }),
        { initialProps: { status: 'running' } }
      )

      setEdges.mockClear()
      rerender({ status: 'paused' })

      // Should call setEdges for enrichment, not cleanup
      expect(setEdges).toHaveBeenCalledTimes(1)
      const updater = setEdges.mock.calls[0][0] as (edges: TestEdge[]) => TestEdge[]
      const result = updater([edgeWithStatus])

      // Edge should still have executionStatus (enrichment, not cleanup)
      expect(result[0].data.executionStatus).toBe('running')
    })

    it('does not clear edge statuses during terminal → terminal transitions (completed → failed)', () => {
      const setEdges = vi.fn()

      const { rerender } = renderHook(
        ({ status }: { status: string | null }) =>
          useEdgeExecutionStatus({
            effectiveExecutionStatus: status,
            isInitialized: true,
            currentWorkflow: emptyWorkflow,
            activityStates: defaultActivity,
            storedEdges: [],
            setEdges,
          }),
        { initialProps: { status: 'completed' } }
      )

      setEdges.mockClear()
      rerender({ status: 'failed' })

      // Should not call setEdges (neither cleanup nor enrichment for terminal states)
      expect(setEdges).not.toHaveBeenCalled()
    })
  })
})
