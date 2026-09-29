import { RhUiMcpServerIcon } from '@patternfly/react-icons'

import { RegistryNodeId } from '../../../../constants'
import { useWorkflowStore } from '../../../../stores/useWorkflowStore'
import { createMcpToolActivity } from '../../../../stores/workflowFactories'
import { parseMcpToolArguments } from '../../node-forms/mcpToolFormSchema'
import { MCPToolNodeForm, type MCPToolFormValues } from '../../node-forms/MCPToolNodeForm'
import { buildNamedActivity } from '../../utils/nodeCreationHelpers'
import { createCustomNode } from '../helpers/nodeTemplates'
import { NodeRegistry } from '../NodeRegistry'

/** Palette label for the MCP tool step. */
export const MCP_TOOL_LABEL = 'MCP tool'

/**
 * Register the MCP tool step type (action category, same as the other executor steps).
 */
export default function registerMCPToolNode() {
  NodeRegistry.register(
    createCustomNode<MCPToolFormValues>(
      {
        id: RegistryNodeId.ACTION_MCP_TOOL,
        label: MCP_TOOL_LABEL,
        icon: RhUiMcpServerIcon,
        category: 'action',
        description: 'Invoke a tool on an MCP server integration',
        keywords: ['mcp', 'tool', 'integration', 'server', 'model context protocol'],
        order: 35,
        formComponent: MCPToolNodeForm,
      },
      (data, onSuccess, onError) => {
        try {
          const toolArguments = parseMcpToolArguments(data.argumentsJson)
          if (toolArguments === undefined) {
            onError('Arguments must be a JSON object')
            return
          }

          const { activityId, activity } = buildNamedActivity(MCP_TOOL_LABEL, data.name, (id, name) =>
            createMcpToolActivity({
              id,
              name,
              integrationId: data.integration_id,
              toolName: data.tool_name,
              arguments: toolArguments,
              timeoutSeconds: data.timeout_seconds,
              settings: data.settings,
            })
          )

          useWorkflowStore.getState().addActivity(activity)
          onSuccess(activityId)
        } catch (error) {
          onError(error instanceof Error ? error.message : 'Failed to add MCP tool step')
        }
      }
    )
  )
}
