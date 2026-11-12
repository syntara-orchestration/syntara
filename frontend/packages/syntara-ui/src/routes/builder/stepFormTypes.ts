import type { MissedSchedulePolicy, NodeSettings } from '@syntara/contracts'

import type { ScriptAffinity } from './utils/scriptExecutionProfile'

export type TriggerFormData = {
  name?: string
  triggerType: string
  scheduleType?: string
  cron?: string
  timezone?: string
  interval?: string
  missedSchedulePolicy?: MissedSchedulePolicy
  eventSource?: string
  eventType?: string
  webhookPath?: string
  inputSchema?: string
  authorizedServiceAccountIds?: string[]
}

export type ActionFormData = {
  name: string
  executor: 'script' | 'http_request'
  // Allow legacy or custom values to round-trip existing data.
  language?: string
  code?: string
  method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE'
  url?: string
  headers?: Array<{ id: string; key: string; value: string }>
  body?: string
  parameters?: string
  requiresApproval?: boolean
  credential_id?: string
  /** Script Execution tab: none lets EP place; required_target pins a target. */
  affinity?: ScriptAffinity
  /** Required when affinity is required_target. */
  execution_target_id?: string
  settings?: NodeSettings
}
