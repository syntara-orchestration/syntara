import { render, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { WorkflowNavigationWebMcpTools } from './WorkflowNavigationWebMcpTools'

const navigate = vi.hoisted(() => vi.fn())
vi.mock('@tanstack/react-router', () => ({ useNavigate: () => navigate }))

const registered: { name: string; execute: (input: unknown) => unknown }[] = []
const registerTool = vi.fn((tool: { name: string; execute: (input: unknown) => unknown }) => {
  registered.push(tool)
})

function setModelContext(context: unknown) {
  Object.defineProperty(document, 'modelContext', { configurable: true, value: context })
}

beforeEach(() => {
  vi.clearAllMocks()
  registered.length = 0
  setModelContext({ registerTool })
  navigate.mockResolvedValue(undefined)
})

afterEach(() => {
  delete (document as Document & { modelContext?: unknown }).modelContext
})

describe('WorkflowNavigationWebMcpTools', () => {
  it('registers a tool that navigates to the blank workflow builder', async () => {
    render(<WorkflowNavigationWebMcpTools canCreate />)
    await waitFor(() => expect(registered).toHaveLength(1))
    expect(registered[0]?.name).toBe('open_new_workflow_builder')
    expect(await registered[0]?.execute({})).toMatchObject({ ok: true, navigated: true, path: '/workflow-builder/new' })
    expect(navigate).toHaveBeenCalledWith({ to: '/workflow-builder/new' })
  })

  it('tracks permission changes and skips registration when creation is unavailable', async () => {
    const view = render(<WorkflowNavigationWebMcpTools canCreate />)
    await waitFor(() => expect(registered).toHaveLength(1))
    view.rerender(<WorkflowNavigationWebMcpTools canCreate={false} />)
    await waitFor(async () => expect(await registered[0]?.execute({})).toMatchObject({ ok: false }))
    expect(navigate).not.toHaveBeenCalled()

    view.unmount()
    registered.length = 0
    registerTool.mockClear()
    render(<WorkflowNavigationWebMcpTools canCreate={false} />)
    expect(registerTool).not.toHaveBeenCalled()
  })
})
