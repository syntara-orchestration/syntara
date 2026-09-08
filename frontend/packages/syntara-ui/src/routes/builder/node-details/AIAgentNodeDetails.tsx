import type { Activity } from '@syntara/contracts'
import type { ReactNode } from 'react'

import { useAlerts } from '../../../providers/alerts'
import { createAgenticActivity, useWorkflowStoreActions } from '../../../stores/useWorkflowStore'
import { AIAgentNodeForm } from '../node-forms/AIAgentNodeForm'
import type { AIAgentFormInitialData, AIAgentFormSubmitData } from '../node-forms/AIAgentNodeForm'

type AIAgentNodeDetailsProps = {
  taskData: Activity
  nodeId: string
  onClose: () => void
  onHeaderContentChange?: (content: ReactNode | null) => void
  projectId?: string
}

/**
 * Side panel for editing a task agent **step** (agentic executor on the canvas).
 * Handles MCP server, tools, model, prompt, and files.
 */
export function AIAgentNodeDetails({
  taskData,
  nodeId,
  onClose,
  onHeaderContentChange,
  projectId,
}: Readonly<AIAgentNodeDetailsProps>) {
  const { showError } = useAlerts()
  // Use action accessor - component won't re-render when store state changes
  const { updateActivity } = useWorkflowStoreActions()

  type AgentConfig = {
    tool_selection_strategy?: 'ALL' | 'NONE' | 'SELECTED'
    tool_selections?: string[]
    tools?: string[]
    integration_connections?: { integration_id: string; credential_id: string }[]
    prompt?: string
    llm_model_id?: string
    file_ids?: string[]
    fileIds?: string[]
    credential_id?: string
    response_schema?: Record<string, unknown>
    responseSchema?: Record<string, unknown>
  }
  // In v2, parameters are at activity.parameters directly (not task.parameters).
  // Some data shapes use a top-level config field for MCP tool config.
  const taskDataExt = taskData as typeof taskData & { config?: AgentConfig }
  const agentConfig = (taskDataExt.config ?? taskData.parameters ?? {}) as AgentConfig

  const toolSelections = agentConfig.tool_selections ?? agentConfig.tools ?? []
  const toolSelectionStrategy = agentConfig.tool_selection_strategy ?? 'NONE'
  const integrationConnections = agentConfig.integration_connections ?? []
  const responseSchema = agentConfig.response_schema ?? agentConfig.responseSchema

  const initialData: AIAgentFormInitialData = {
    name: taskData.name,
    llm_model_id: agentConfig.llm_model_id ?? '',
    prompt: agentConfig.prompt ?? '',
    tool_selection_strategy: toolSelectionStrategy,
    tool_selections: toolSelections,
    integration_connections: integrationConnections,
    credential_id: agentConfig.credential_id ?? undefined,
    responseSchema: responseSchema ? JSON.stringify(responseSchema, null, 2) : undefined,
    settings: taskData.settings,
  }

  const existingFileIds = agentConfig.file_ids ?? agentConfig.fileIds ?? []

  const handleSubmit = (data: AIAgentFormSubmitData): boolean => {
    try {
      const updatedActivity = createAgenticActivity({
        id: nodeId,
        name: data.name,
        toolSelectionStrategy: data.tool_selection_strategy,
        toolSelections: data.tool_selections,
        integrationConnections:
          data.integration_connections && data.integration_connections.length > 0
            ? data.integration_connections
            : undefined,
        prompt: data.prompt ?? undefined,
        llmModelId: data.llm_model_id ?? undefined,
        fileIds: data.fileIds.length > 0 ? data.fileIds : undefined,
        credentialId: data.credential_id ?? undefined,
        responseSchema: data.parsedResponseSchema,
        settings: data.settings,
      })

      updateActivity(nodeId, updatedActivity)
      onClose()
      return true
    } catch (error) {
      showError({
        title: 'Update failed',
        description: error instanceof Error ? error.message : 'Failed to update task agent step',
      })
      return false
    }
  }

  return (
    <AIAgentNodeForm
      initialData={initialData}
      existingFileIds={existingFileIds}
      onSubmit={handleSubmit}
      onHeaderContentChange={onHeaderContentChange}
      projectId={projectId}
    />
  )
}
