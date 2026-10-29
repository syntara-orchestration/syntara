import type { EdgeConnection } from './types/edge'

export type ToolDefinition = {
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

export type CanvasConnectionInput = {
  edgeId?: string
  source: string
  target: string
  sourceHandle?: string
  targetHandle?: string
}

export type CanvasConnectionResult = { ok: true; connection: EdgeConnection } | { ok: false; message: string }

export type WorkflowCanvasActions = {
  canEdit: boolean
  deleteCanvasNode: (nodeId: string) => Promise<string[]>
  deleteCanvasConnection: (edgeId: string) => Promise<boolean>
  saveCanvasConnection: (input: CanvasConnectionInput) => CanvasConnectionResult
}
