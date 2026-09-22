import { z } from 'zod'

import { nodeSettingsSchema } from './shared/nodeSettingsSchema'

/** Backend bounds for `timeout_seconds` on an `mcp_tool` node (MCPToolExecutorParameters). */
const MCP_TOOL_TIMEOUT_MIN_SECONDS = 1
const MCP_TOOL_TIMEOUT_MAX_SECONDS = 600

/** Parses the arguments editor contents; `undefined` means "not a JSON object". */
export function parseMcpToolArguments(raw: string | undefined): Record<string, unknown> | undefined {
  if (raw === undefined || raw.trim() === '') return {}
  let parsed: unknown
  try {
    parsed = JSON.parse(raw)
  } catch {
    return undefined
  }
  if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) return undefined
  return parsed as Record<string, unknown>
}

/**
 * Zod schema for the MCP tool node form.
 *
 * `arguments` is edited as JSON text and validated to be a JSON object; it is
 * parsed into `MCPToolExecutorParameters.arguments` on submit.
 */
export const mcpToolFormSchema = z.object({
  name: z.string(),
  integration_id: z.string().min(1, { message: 'Select an MCP server integration' }),
  tool_name: z.string().min(1, { message: 'Select a tool' }),
  argumentsJson: z
    .string()
    .optional()
    .refine((value) => parseMcpToolArguments(value) !== undefined, {
      message: 'Arguments must be a JSON object, e.g. {"path": "/tmp"}',
    }),
  timeout_seconds: z
    .number()
    .int({ message: 'Timeout must be a whole number of seconds' })
    .min(MCP_TOOL_TIMEOUT_MIN_SECONDS, { message: `Timeout must be at least ${MCP_TOOL_TIMEOUT_MIN_SECONDS} second` })
    .max(MCP_TOOL_TIMEOUT_MAX_SECONDS, {
      message: `Timeout cannot exceed ${MCP_TOOL_TIMEOUT_MAX_SECONDS} seconds`,
    })
    .optional(),
  settings: nodeSettingsSchema.optional(),
})

export type MCPToolFormData = z.infer<typeof mcpToolFormSchema>
export type MCPToolFormValues = z.input<typeof mcpToolFormSchema>
