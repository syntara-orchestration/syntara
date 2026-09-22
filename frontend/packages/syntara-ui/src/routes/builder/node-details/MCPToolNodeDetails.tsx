import type { Activity } from '@syntara/contracts'
import type { ReactNode } from 'react'

import { useAlerts } from '../../../providers/alerts'
import { useWorkflowStoreActions } from '../../../stores/useWorkflowStore'
import { parseMcpToolArguments } from '../node-forms/mcpToolFormSchema'
import { MCPToolNodeForm, type MCPToolFormValues } from '../node-forms/MCPToolNodeForm'

type MCPToolNodeDetailsProps = {
  taskData: Activity
  nodeId: string
  onClose: () => void
  onHeaderContentChange?: (content: ReactNode | null) => void
  projectId?: string
}

function toStringValue(value: unknown): string {
  return typeof value === 'string' ? value : ''
}

function toArgumentsJson(value: unknown): string {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) return ''
  if (Object.keys(value).length === 0) return ''
  return JSON.stringify(value, null, 2)
}

function toTimeoutSeconds(value: unknown): number | undefined {
  return typeof value === 'number' && Number.isFinite(value) ? value : undefined
}

/** Edit-mode panel for an existing `mcp_tool` step. */
export function MCPToolNodeDetails({
  taskData,
  nodeId,
  onClose,
  onHeaderContentChange,
  projectId,
}: Readonly<MCPToolNodeDetailsProps>) {
  const { showError } = useAlerts()
  const { updateActivity } = useWorkflowStoreActions()

  const parameters: Record<string, unknown> = taskData.parameters ?? {}

  const initialData: Partial<MCPToolFormValues> = {
    name: taskData.name ?? '',
    integration_id: toStringValue(parameters.integration_id),
    tool_name: toStringValue(parameters.tool_name),
    argumentsJson: toArgumentsJson(parameters.arguments),
    timeout_seconds: toTimeoutSeconds(parameters.timeout_seconds),
    settings: taskData.settings,
  }

  const handleSubmit = (data: MCPToolFormValues) => {
    const toolArguments = parseMcpToolArguments(data.argumentsJson)
    if (toolArguments === undefined) {
      showError({ title: 'Cannot save MCP tool step', description: 'Arguments must be a JSON object' })
      return
    }

    const updatedActivity = {
      ...taskData,
      name: data.name,
      parameters: {
        integration_id: data.integration_id,
        tool_name: data.tool_name,
        arguments: toolArguments,
        ...(data.timeout_seconds !== undefined && { timeout_seconds: data.timeout_seconds }),
      },
      settings: data.settings,
    } as Activity

    updateActivity(nodeId, updatedActivity)
    onClose()
  }

  return (
    <MCPToolNodeForm
      initialData={initialData}
      onSubmit={handleSubmit}
      onHeaderContentChange={onHeaderContentChange}
      projectId={projectId}
    />
  )
}
