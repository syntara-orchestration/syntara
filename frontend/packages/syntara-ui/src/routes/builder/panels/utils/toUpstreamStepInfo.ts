import type { UpstreamStepInfo } from '../hooks/useUpstreamSteps'

type UpstreamStepSource = {
  id: string
  name?: string
  type: string
  parameters?: Record<string, unknown>
}

/** Describe an activity or trigger as an upstream step, keeping `name` as stored. */
export function toUpstreamStepInfo(node: UpstreamStepSource): UpstreamStepInfo {
  return { id: node.id, name: node.name, type: node.type, parameters: node.parameters }
}
