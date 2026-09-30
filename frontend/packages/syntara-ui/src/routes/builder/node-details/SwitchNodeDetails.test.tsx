import { EdgeHandleEnum, type SwitchActivity } from '@syntara/contracts'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { renderWithHeader } from '../node-forms/test-utils/renderWithHeader'

import { SwitchNodeDetails } from './SwitchNodeDetails'

let uuidCounter = 0
vi.mock('../../../utils/generateUUID', () => ({
  generateUUID: () => `stable-uuid-${uuidCounter++}`,
}))

const mockUpdateSwitchActivity = vi.fn()

vi.mock('../../../stores/useWorkflowStore', () => ({
  useWorkflowStore: Object.assign(
    (selector: (state: Record<string, unknown>) => unknown) =>
      selector({ currentWorkflow: null, isDirty: false, edges: [] }),
    {
      getState: () => ({}),
    }
  ),
  useWorkflowStoreActions: () => ({
    updateSwitchActivity: mockUpdateSwitchActivity,
  }),
}))

vi.mock('../../../providers/alerts', () => ({
  useAlerts: () => ({
    showError: vi.fn(),
    showSuccess: vi.fn(),
  }),
}))

describe('SwitchNodeDetails', () => {
  const baseSwitchData: SwitchActivity = {
    id: 'switch-1',
    type: 'switch',
    name: 'Route Request',
    parameters: {
      cases: [
        { port: 'case_0', label: 'Path 1', condition: '${trigger.priority} > 7' },
        { port: 'case_1', label: 'Path 2', condition: '${trigger.status} == "rejected"' },
      ],
      default_port: EdgeHandleEnum.DEFAULT,
    },
  }

  const mockOnClose = vi.fn()

  beforeEach(() => {
    vi.clearAllMocks()
    uuidCounter = 0
  })

  describe('Rendering', () => {
    it('renders the switch form with pre-populated data', () => {
      renderWithHeader(<SwitchNodeDetails switchData={baseSwitchData} nodeId="switch-1" onClose={mockOnClose} />)

      expect(screen.getByPlaceholderText(/Enter activity name/i)).toHaveValue('Route Request')
    })

    it('renders path labels from backend config', () => {
      renderWithHeader(<SwitchNodeDetails switchData={baseSwitchData} nodeId="switch-1" onClose={mockOnClose} />)

      expect(screen.getByDisplayValue('Path 1')).toBeInTheDocument()
      expect(screen.getByDisplayValue('Path 2')).toBeInTheDocument()
    })

    it('renders with empty config gracefully', () => {
      const emptySwitch: SwitchActivity = {
        id: 'switch-empty',
        type: 'switch',
        name: 'Empty Switch',
        parameters: { cases: [], default_port: EdgeHandleEnum.DEFAULT },
      }

      renderWithHeader(<SwitchNodeDetails switchData={emptySwitch} nodeId="switch-empty" onClose={mockOnClose} />)

      expect(screen.getByPlaceholderText(/Enter activity name/i)).toHaveValue('Empty Switch')
    })

    it('renders with missing config gracefully', () => {
      const noConfigSwitch = {
        id: 'switch-no-config',
        type: 'switch',
        name: 'No Config',
        parameters: {},
      } as unknown as SwitchActivity

      renderWithHeader(
        <SwitchNodeDetails switchData={noConfigSwitch} nodeId="switch-no-config" onClose={mockOnClose} />
      )

      expect(screen.getByPlaceholderText(/Enter activity name/i)).toHaveValue('No Config')
    })
  })

  describe('Expression parsing', () => {
    it('parses simple equality condition', () => {
      const switchWithEquality: SwitchActivity = {
        id: 'switch-eq',
        type: 'switch',
        name: 'Equality Check',
        parameters: {
          cases: [{ port: 'case_0', label: 'Path 1', condition: '${status} == "active"' }],
          default_port: EdgeHandleEnum.DEFAULT,
        },
      }

      renderWithHeader(<SwitchNodeDetails switchData={switchWithEquality} nodeId="switch-eq" onClose={mockOnClose} />)

      expect(screen.getByPlaceholderText(/Enter activity name/i)).toHaveValue('Equality Check')
    })

    it('handles unparseable condition as fallback', () => {
      const switchWithComplex: SwitchActivity = {
        id: 'switch-complex',
        type: 'switch',
        name: 'Complex',
        parameters: {
          cases: [{ port: 'case_0', label: 'Path 1', condition: 'some_complex && expression || thing' }],
          default_port: EdgeHandleEnum.DEFAULT,
        },
      }

      renderWithHeader(
        <SwitchNodeDetails switchData={switchWithComplex} nodeId="switch-complex" onClose={mockOnClose} />
      )

      expect(screen.getByPlaceholderText(/Enter activity name/i)).toHaveValue('Complex')
    })

    it('parses negated condition correctly', () => {
      const switchWithNot: SwitchActivity = {
        id: 'switch-not',
        type: 'switch',
        name: 'Negated',
        parameters: {
          cases: [{ port: 'case_0', label: 'Path 1', condition: 'not (${status} == "active")' }],
          default_port: EdgeHandleEnum.DEFAULT,
        },
      }

      renderWithHeader(<SwitchNodeDetails switchData={switchWithNot} nodeId="switch-not" onClose={mockOnClose} />)

      expect(screen.getByPlaceholderText(/Enter activity name/i)).toHaveValue('Negated')
    })
  })

  describe('Header content', () => {
    it('calls onHeaderContentChange', () => {
      const mockOnHeaderContentChange = vi.fn()
      render(
        <SwitchNodeDetails
          switchData={baseSwitchData}
          nodeId="switch-1"
          onClose={mockOnClose}
          onHeaderContentChange={mockOnHeaderContentChange}
        />
      )

      expect(mockOnHeaderContentChange).toHaveBeenCalledWith(expect.anything())
    })
  })

  describe('Edge remapping on submit', () => {
    it('remaps surviving edges when middle case is deleted', async () => {
      const threeCaseSwitch: SwitchActivity = {
        id: 'switch-1',
        type: 'switch',
        name: 'Three Cases',
        parameters: {
          cases: [
            { port: 'case_0', label: 'Path A', condition: '${trigger.a} == "1"' },
            { port: 'case_1', label: 'Path B', condition: '${trigger.b} == "2"' },
            { port: 'case_2', label: 'Path C', condition: '${trigger.c} == "3"' },
          ],
          default_port: EdgeHandleEnum.DEFAULT,
        },
      }

      const user = userEvent.setup()
      renderWithHeader(<SwitchNodeDetails switchData={threeCaseSwitch} nodeId="switch-1" onClose={mockOnClose} />)

      const removeButtons = screen.getAllByRole('button', { name: /remove path/i })
      await user.click(removeButtons[1])

      fireEvent.submit(screen.getByTestId('switch-node-form'))

      await waitFor(() => {
        expect(mockUpdateSwitchActivity).toHaveBeenCalled()
      })

      const [nodeId, activity, portMapping] = mockUpdateSwitchActivity.mock.calls[0] as [
        string,
        SwitchActivity,
        Map<string, string>,
      ]
      expect(nodeId).toBe('switch-1')
      expect(activity.parameters.cases).toHaveLength(2)
      expect(portMapping.get('case_0')).toBe('case_0')
      expect(portMapping.get('case_2')).toBe('case_1')
      expect(portMapping.has('case_1')).toBe(false)
    })

    it('calls updateSwitchActivity with correct port mapping on submit', async () => {
      renderWithHeader(<SwitchNodeDetails switchData={baseSwitchData} nodeId="switch-1" onClose={mockOnClose} />)

      fireEvent.submit(screen.getByTestId('switch-node-form'))

      await waitFor(() => {
        expect(mockUpdateSwitchActivity).toHaveBeenCalled()
      })

      const [nodeId, activity, portMapping] = mockUpdateSwitchActivity.mock.calls[0] as [
        string,
        SwitchActivity,
        Map<string, string>,
      ]
      expect(nodeId).toBe('switch-1')
      expect(activity.parameters.cases).toHaveLength(2)
      expect(portMapping.get('case_0')).toBe('case_0')
      expect(portMapping.get('case_1')).toBe('case_1')
    })

    it('closes the panel after successful submit', async () => {
      renderWithHeader(<SwitchNodeDetails switchData={baseSwitchData} nodeId="switch-1" onClose={mockOnClose} />)

      fireEvent.submit(screen.getByTestId('switch-node-form'))

      await waitFor(() => {
        expect(mockOnClose).toHaveBeenCalled()
      })
    })
  })
})
