import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import type { NodeKind } from '../../../hooks/useNodeKindsQuery'

import { NodeKindStatementBuilder } from './NodeKindStatementBuilder'

const { mockNodeKinds } = vi.hoisted(() => ({ mockNodeKinds: { current: [] as unknown[] } }))

vi.mock('../../../hooks/useNodeKindsQuery', () => ({
  useNodeKindsQuery: () => ({
    query: { isPending: false },
    nodeKinds: mockNodeKinds.current,
    nodeKindByKind: new Map(),
    disabledKinds: new Set<string>(),
  }),
}))

function kind(overrides: Partial<NodeKind> & { kind: string }): NodeKind {
  return {
    category: 'action',
    enabled: true,
    switchable: true,
    deniable_actions: ['write', 'execute'],
    can_write: true,
    attributes: [],
    ...overrides,
  }
}

beforeEach(() => {
  mockNodeKinds.current = [
    kind({ kind: 'script', attributes: [{ name: 'language', allowed_values: ['python', 'bash'] }] }),
    kind({ kind: 'mcp_tool', attributes: [{ name: 'tool_name', allowed_values: null }] }),
    kind({ kind: 'manual_trigger', category: 'trigger', deniable_actions: ['write'] }),
    kind({ kind: 'condition', category: 'flow_control', switchable: false, deniable_actions: [] }),
  ]
})

async function selectKind(user: ReturnType<typeof userEvent.setup>, label: string) {
  await user.click(screen.getByRole('button', { name: /Select a node kind|script|mcp_tool|manual_trigger/ }))
  await user.click(await screen.findByRole('option', { name: label }))
}

describe('NodeKindStatementBuilder', () => {
  it('offers only kinds that may be denied for the selected action', async () => {
    const user = userEvent.setup()
    render(<NodeKindStatementBuilder statementsJson="[]" onAppend={vi.fn()} />)

    await user.click(screen.getByRole('button', { name: 'Select a node kind' }))

    expect(await screen.findByRole('option', { name: 'script' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'manual_trigger' })).toBeInTheDocument()
    expect(screen.queryByRole('option', { name: 'condition' })).not.toBeInTheDocument()
  })

  it('appends a well-formed deny statement to the JSON', async () => {
    const onAppend = vi.fn()
    const user = userEvent.setup()
    render(<NodeKindStatementBuilder statementsJson="[]" onAppend={onAppend} />)

    await selectKind(user, 'script')
    await user.click(screen.getByRole('button', { name: 'Append to statements JSON' }))

    expect(JSON.parse(onAppend.mock.calls[0][0] as string)).toEqual([
      {
        effect: 'deny',
        actions: ['workflow_node:write'],
        scope: 'project',
        conditions: { resource_labels: { kind: 'script' } },
      },
    ])
  })

  it('renders select and text attributes declared by the selected kind', async () => {
    const user = userEvent.setup()
    render(<NodeKindStatementBuilder statementsJson="[]" onAppend={vi.fn()} />)

    await selectKind(user, 'script')

    expect(screen.getByRole('button', { name: 'Any value' })).toBeInTheDocument()
    expect(screen.getByText('Optional. Leave empty to match every value.')).toBeInTheDocument()

    await selectKind(user, 'mcp_tool')

    expect(screen.getByRole('textbox', { name: 'tool_name' })).toBeInTheDocument()
  })

  it('appends normalized attributes and previews the exact statement JSON', async () => {
    const onAppend = vi.fn()
    const user = userEvent.setup()
    render(<NodeKindStatementBuilder statementsJson="[]" onAppend={onAppend} />)

    await selectKind(user, 'script')
    await user.click(screen.getByRole('button', { name: 'Any value' }))
    await user.click(await screen.findByRole('option', { name: 'python' }))

    const preview = screen.getByLabelText('Preview of the statement to append')
    expect(preview).toHaveTextContent('"effect": "deny"')
    expect(preview).toHaveTextContent('"workflow_node:write"')
    expect(preview).toHaveTextContent('"kind": "script"')
    expect(preview).toHaveTextContent('"language": "python"')

    await user.click(screen.getByRole('button', { name: 'Append to statements JSON' }))
    const appendedStatement: unknown = JSON.parse(onAppend.mock.calls[0][0] as string)
    expect(appendedStatement).toEqual([
      {
        effect: 'deny',
        actions: ['workflow_node:write'],
        scope: 'project',
        conditions: { resource_labels: { kind: 'script', language: 'python' } },
      },
    ])
  })

  it('resets attribute values when the kind changes', async () => {
    const user = userEvent.setup()
    render(<NodeKindStatementBuilder statementsJson="[]" onAppend={vi.fn()} />)

    await selectKind(user, 'script')
    await user.click(screen.getByRole('button', { name: 'Any value' }))
    await user.click(await screen.findByRole('option', { name: 'bash' }))
    await selectKind(user, 'mcp_tool')
    await user.type(screen.getByRole('textbox', { name: 'tool_name' }), 'Ping')
    await selectKind(user, 'script')

    expect(screen.getByRole('button', { name: 'Any value' })).toBeInTheDocument()
    expect(screen.getByLabelText('Preview of the statement to append')).not.toHaveTextContent('"language": "bash"')
  })

  it('does nothing until a node kind is chosen', async () => {
    const onAppend = vi.fn()
    const user = userEvent.setup()
    render(<NodeKindStatementBuilder statementsJson="[]" onAppend={onAppend} />)

    await user.click(screen.getByRole('button', { name: 'Append to statements JSON' }))

    expect(onAppend).not.toHaveBeenCalled()
  })

  it('reports invalid JSON instead of discarding it', async () => {
    const onAppend = vi.fn()
    const user = userEvent.setup()
    render(<NodeKindStatementBuilder statementsJson="not json" onAppend={onAppend} />)

    await selectKind(user, 'script')
    await user.click(screen.getByRole('button', { name: 'Append to statements JSON' }))

    expect(onAppend).not.toHaveBeenCalled()
    expect(await screen.findByText(/Fix the statements JSON/)).toBeInTheDocument()
  })

  it('offers every kind once the effect is allow', async () => {
    const user = userEvent.setup()
    render(<NodeKindStatementBuilder statementsJson="[]" onAppend={vi.fn()} />)

    await user.click(screen.getByRole('button', { name: 'Deny' }))
    await user.click(await screen.findByRole('option', { name: 'Allow' }))
    await user.click(screen.getByRole('button', { name: 'Select a node kind' }))

    expect(await screen.findByRole('option', { name: 'condition' })).toBeInTheDocument()
  })

  it('shows append feedback and clears it when a choice changes', async () => {
    const user = userEvent.setup()
    render(<NodeKindStatementBuilder statementsJson="[]" onAppend={vi.fn()} />)

    await selectKind(user, 'script')
    await user.click(screen.getByRole('button', { name: 'Append to statements JSON' }))
    expect(screen.getByText('Statement appended to the Policy statements JSON below.')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Deny' }))
    await user.click(await screen.findByRole('option', { name: 'Allow' }))
    expect(screen.queryByText('Statement appended to the Policy statements JSON below.')).not.toBeInTheDocument()
  })

  it('renders the helper as a labelled panel', () => {
    render(<NodeKindStatementBuilder statementsJson="[]" onAppend={vi.fn()} />)

    expect(screen.getByRole('heading', { name: 'Statement helper' })).toBeInTheDocument()
    expect(screen.getByText('optional')).toBeInTheDocument()
  })

  it('has no accessibility violations', async () => {
    const { container } = render(<NodeKindStatementBuilder statementsJson="[]" onAppend={vi.fn()} />)

    expect(await axe(container)).toHaveNoViolations()
  })
})
