import type { Approval, FormsAPI } from '@syntara/contracts'
import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { ExecutionDetailSidePanel } from './ExecutionDetailSidePanel'

vi.mock('./FormPromptSidePanel', () => ({
  FormPromptSidePanel: ({ formPrompt }: { formPrompt: { id: string } }) => (
    <div data-testid="form-prompt-panel">Form prompt {formPrompt.id}</div>
  ),
}))

vi.mock('./ApprovalSidePanel', () => ({
  ApprovalSidePanel: ({ approval }: { approval: { id: string } }) => (
    <div data-testid="approval-panel">Approval {approval.id}</div>
  ),
}))

const mockFormPrompt: FormsAPI.components['schemas']['FormPromptSummary'] = {
  id: 'fp-1',
  execution_id: 'exec-1',
  project_id: 'proj-1',
  prompt_node_id: 'form_a',
  name: 'Form A',
  status: 'pending',
  temporal_activity_id: 'act-1',
}

const mockApproval: Approval = {
  id: 'approval-1',
  project_id: 'project-1',
  name: 'Test Approval',
  status: 'pending',
  execution_id: 'exec-1',
  approval_node_id: 'node-1',
  created_at: '2026-01-01T00:00:00Z',
  next_step_approved: { id: 'step-a', name: 'Approved Step', type: 'task' },
  workflow_context: {
    workflow_id: 'wfv-1',
    workflow_name: 'Test Workflow',
    inputs: {},
  },
}

const navigation = {
  current: null,
  currentIndex: 0,
  total: 0,
  hasPrev: false,
  hasNext: false,
  navigatePrev: vi.fn(),
  navigateNext: vi.fn(),
}

const baseProps = {
  formPromptPanelOpen: false,
  currentFormPrompt: null,
  formPromptNavigation: navigation,
  formPromptIndex: 0,
  formPromptCount: 0,
  executionId: 'exec-1',
  activityNameMap: new Map<string, string>(),
  onFormPromptClose: vi.fn(),
  onFormPromptSubmitted: vi.fn(),
  approvalPanelOpen: false,
  currentApproval: null,
  approvalMessage: undefined,
  approvalNavigation: navigation,
  currentApprovalIndex: 0,
  approvalCount: 0,
  onApprovalClose: vi.fn(),
  onApprovalDecisionSubmitted: vi.fn(),
  onNavigate: vi.fn(),
}

describe('ExecutionDetailSidePanel', () => {
  it('renders form prompt panel when open with a current prompt', () => {
    render(
      <ExecutionDetailSidePanel
        {...baseProps}
        formPromptPanelOpen
        currentFormPrompt={mockFormPrompt}
        formPromptCount={1}
      />
    )

    expect(screen.getByTestId('form-prompt-panel')).toHaveTextContent('Form prompt fp-1')
    expect(screen.queryByTestId('approval-panel')).not.toBeInTheDocument()
  })

  it('renders approval panel when open with a current approval', () => {
    render(
      <ExecutionDetailSidePanel {...baseProps} approvalPanelOpen currentApproval={mockApproval} approvalCount={1} />
    )

    expect(screen.getByTestId('approval-panel')).toHaveTextContent('Approval approval-1')
    expect(screen.queryByTestId('form-prompt-panel')).not.toBeInTheDocument()
  })

  it('prefers form prompt panel when both panels would be open', () => {
    render(
      <ExecutionDetailSidePanel
        {...baseProps}
        formPromptPanelOpen
        currentFormPrompt={mockFormPrompt}
        approvalPanelOpen
        currentApproval={mockApproval}
      />
    )

    expect(screen.getByTestId('form-prompt-panel')).toBeInTheDocument()
    expect(screen.queryByTestId('approval-panel')).not.toBeInTheDocument()
  })

  it('returns null when no panel is active', () => {
    const { container } = render(<ExecutionDetailSidePanel {...baseProps} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('does not render form prompt panel when open flag is set without a prompt', () => {
    const { container } = render(<ExecutionDetailSidePanel {...baseProps} formPromptPanelOpen />)
    expect(container).toBeEmptyDOMElement()
  })
})
