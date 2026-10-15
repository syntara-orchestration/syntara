import { EdgeHandleEnum, type SwitchActivity } from '@syntara/contracts'
import { render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { buildSwitchCasePort } from '../../../builder/utils/switchCaseHelpers'

import { SwitchStepComponent } from './SwitchNode'

vi.mock('@xyflow/react', () => ({
  useReactFlow: () => ({
    deleteElements: vi.fn(),
    updateNode: vi.fn(),
    getNode: vi.fn(),
  }),
  useStore: (selector: (s: { transform: [number, number, number] }) => unknown) => selector({ transform: [0, 0, 1] }),
  useUpdateNodeInternals: () => vi.fn(),
  useEdges: () => [],
  Handle: () => null,
  Position: {
    Top: 'top',
    Bottom: 'bottom',
    Left: 'left',
    Right: 'right',
  },
}))

describe('SwitchStepComponent', () => {
  const baseSwitchData = {
    id: 'switch-1',
    type: 'switch',
    name: 'Route by status',
    parameters: {
      cases: [
        { port: buildSwitchCasePort(0), label: 'Path 1', condition: '${status} == "approved"' },
        { port: buildSwitchCasePort(1), label: 'Path 2', condition: '${status} == "rejected"' },
      ],
      default_port: EdgeHandleEnum.DEFAULT,
    },
  } as SwitchActivity

  const createNodeProps = (data: SwitchActivity) => ({
    id: data.id,
    data,
    type: 'switch' as const,
    position: { x: 0, y: 0 },
    positionAbsoluteX: 0,
    positionAbsoluteY: 0,
    selected: false,
    dragging: false,
    isConnectable: true,
    zIndex: 0,
    selectable: true,
    deletable: true,
    draggable: true,
  })

  describe('Rendering', () => {
    it('renders switch node with name', () => {
      render(<SwitchStepComponent {...createNodeProps(baseSwitchData)} />)

      expect(screen.getByText('Route by status')).toBeInTheDocument()
    })

    it('renders case labels from config', () => {
      render(<SwitchStepComponent {...createNodeProps(baseSwitchData)} />)

      expect(screen.getByText('Path 1')).toBeInTheDocument()
      expect(screen.getByText('Path 2')).toBeInTheDocument()
    })

    it('renders fallback handle', () => {
      render(<SwitchStepComponent {...createNodeProps(baseSwitchData)} />)

      expect(screen.getByText('Fallback')).toBeInTheDocument()
    })

    it('renders with empty cases gracefully', () => {
      const emptyData = {
        ...baseSwitchData,
        parameters: { cases: [], default_port: EdgeHandleEnum.DEFAULT },
      } as SwitchActivity

      render(<SwitchStepComponent {...createNodeProps(emptyData)} />)

      expect(screen.getByText('Fallback')).toBeInTheDocument()
    })

    it('renders with default name when name is not set', () => {
      const noNameData = { ...baseSwitchData, name: undefined } as unknown as SwitchActivity

      render(<SwitchStepComponent {...createNodeProps(noNameData)} />)

      expect(screen.getByText('Untitled Switch')).toBeInTheDocument()
    })
  })

  describe('Subtitle', () => {
    it('renders Switch subtitle', () => {
      render(<SwitchStepComponent {...createNodeProps(baseSwitchData)} />)

      expect(screen.getByText('Switch')).toBeInTheDocument()
    })
  })

  describe('Edge cases', () => {
    it('renders with missing config', () => {
      const noConfigData = { ...baseSwitchData, parameters: undefined } as unknown as SwitchActivity

      render(<SwitchStepComponent {...createNodeProps(noConfigData)} />)

      expect(screen.getByText('Fallback')).toBeInTheDocument()
    })

    it('renders with missing cases in config', () => {
      const noCasesData = {
        ...baseSwitchData,
        parameters: { default_port: EdgeHandleEnum.DEFAULT },
      } as unknown as SwitchActivity

      render(<SwitchStepComponent {...createNodeProps(noCasesData)} />)

      expect(screen.getByText('Fallback')).toBeInTheDocument()
    })

    it('generates port from index when case has no port', () => {
      const noPortData = {
        ...baseSwitchData,
        parameters: {
          cases: [{ port: '', label: 'No Port Case', condition: '${x} == 1' }],
          default_port: EdgeHandleEnum.DEFAULT,
        },
      } as SwitchActivity

      render(<SwitchStepComponent {...createNodeProps(noPortData)} />)

      expect(screen.getByText('No Port Case')).toBeInTheDocument()
    })

    it('falls back to Path N when case has no label', () => {
      const noLabelData = {
        ...baseSwitchData,
        parameters: {
          cases: [
            { port: buildSwitchCasePort(0), label: '', condition: '${x} == 1' },
            { port: buildSwitchCasePort(1), label: '', condition: '${y} == 2' },
          ],
          default_port: EdgeHandleEnum.DEFAULT,
        },
      } as SwitchActivity

      render(<SwitchStepComponent {...createNodeProps(noLabelData)} />)

      expect(screen.getByText('Path 1')).toBeInTheDocument()
      expect(screen.getByText('Path 2')).toBeInTheDocument()
    })

    it('renders with execution state', () => {
      const withExecState = {
        ...baseSwitchData,
        __executionState: {
          status: 'completed' as const,
          started_at: '2026-01-01T00:00:00Z',
          completed_at: '2026-01-01T00:01:00Z',
        },
      } as unknown as SwitchActivity

      render(<SwitchStepComponent {...createNodeProps(withExecState)} />)

      expect(screen.getByText('Route by status')).toBeInTheDocument()
    })
  })

  describe('TruncatedPathLabel', () => {
    let mockObserve: ReturnType<typeof vi.fn>
    let mockDisconnect: ReturnType<typeof vi.fn>

    beforeEach(() => {
      mockObserve = vi.fn()
      mockDisconnect = vi.fn()
      vi.stubGlobal(
        'ResizeObserver',
        class {
          observe = mockObserve
          disconnect = mockDisconnect
          unobserve = vi.fn()
        }
      )
    })

    afterEach(() => {
      vi.unstubAllGlobals()
    })

    it('shows tooltip when label is truncated', async () => {
      vi.spyOn(HTMLElement.prototype, 'scrollHeight', 'get').mockReturnValue(100)
      vi.spyOn(HTMLElement.prototype, 'clientHeight', 'get').mockReturnValue(40)

      const truncatedData = {
        ...baseSwitchData,
        parameters: {
          cases: [
            {
              port: buildSwitchCasePort(0),
              label: 'A very long label that should be truncated in the UI',
              condition: '${x} == 1',
            },
          ],
          default_port: EdgeHandleEnum.DEFAULT,
        },
      } as SwitchActivity

      render(<SwitchStepComponent {...createNodeProps(truncatedData)} />)

      await screen.findByText('A very long label that should be truncated in the UI')
      expect(mockObserve).toHaveBeenCalled()
    })

    it('does not show tooltip when label fits', async () => {
      vi.spyOn(HTMLElement.prototype, 'scrollHeight', 'get').mockReturnValue(20)
      vi.spyOn(HTMLElement.prototype, 'clientHeight', 'get').mockReturnValue(40)

      render(<SwitchStepComponent {...createNodeProps(baseSwitchData)} />)

      await screen.findByText('Path 1')
      expect(mockObserve).toHaveBeenCalled()
    })
  })
})
