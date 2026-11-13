import { useNavigate } from '@tanstack/react-router'
import { useEffect, useRef } from 'react'

import { detachPromise } from '../../utils/detachPromise'

type ToolDefinition = {
  name: string
  description: string
  inputSchema: Record<string, unknown>
  annotations: {
    readOnlyHint: boolean
    untrustedContentHint: boolean
    consequentialHint: boolean
  }
  execute: (input: unknown) => unknown
}

type ModelContext = {
  registerTool: (tool: ToolDefinition, options?: { signal?: AbortSignal }) => void | Promise<void>
}

type WorkflowNavigationWebMcpToolsProps = {
  canCreate: boolean
}

const EMPTY_SCHEMA = { type: 'object', properties: {}, additionalProperties: false }

function isModelContext(value: unknown): value is ModelContext {
  return !!value && typeof value === 'object' && 'registerTool' in value && typeof value.registerTool === 'function'
}

export function WorkflowNavigationWebMcpTools({ canCreate }: WorkflowNavigationWebMcpToolsProps) {
  const navigate = useNavigate()
  const actionsRef = useRef({ canCreate })

  useEffect(() => {
    actionsRef.current = { canCreate }
  }, [canCreate])

  useEffect(() => {
    if (!canCreate || typeof document === 'undefined') return
    const modelContextValue = 'modelContext' in document ? document.modelContext : undefined
    if (!isModelContext(modelContextValue)) return

    const controller = new AbortController()
    const tool: ToolDefinition = {
      name: 'open_new_workflow_builder',
      description:
        'Open a blank workflow builder in Syntara. Use this before creating a new workflow draft. This does not save or run a workflow.',
      inputSchema: EMPTY_SCHEMA,
      annotations: { readOnlyHint: false, untrustedContentHint: false, consequentialHint: false },
      execute: async () => {
        const actions = actionsRef.current
        if (!actions.canCreate) return { ok: false, message: 'You do not have permission to create workflows here.' }
        await navigate({ to: '/workflow-builder/new' })
        return {
          ok: true,
          navigated: true,
          path: '/workflow-builder/new',
          message: 'Opened a blank workflow builder. Continue with its workflow tools.',
        }
      },
    }

    detachPromise(
      Promise.resolve(modelContextValue.registerTool(tool, { signal: controller.signal })).catch(() => undefined)
    )
    return () => controller.abort()
  }, [canCreate, navigate])

  return null
}
