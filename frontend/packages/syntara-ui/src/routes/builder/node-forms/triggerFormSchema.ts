import { MissedSchedulePolicyEnum, ScheduleTypeEnum, TriggerTypeEnum, WEBHOOK_TRIGGER_TYPES } from '@syntara/contracts'
import { z } from 'zod'

import { safeJSONReviver } from '../../../utils/jsonSafeParse'
import { parseRepeatingInterval } from '../../../utils/triggerFormatting'
import { isValidWebhookPath } from '../../../utils/webhookPath'

const subWorkflowOutputFieldSchema = z.object({
  path: z.string().max(256),
  type: z.enum(['string', 'number', 'boolean', 'object', 'array', 'unknown']),
  required: z.boolean(),
  description: z.string().optional(),
  expression: z.string().optional(),
})

/**
 * Zod schema for the Trigger node form.
 * Manual and webhook fields stay optional so incomplete triggers can be added
 * (advisory save). Scheduled interval/cron must be present because the backend
 * schema requires them; omitting them produces a save-time schema error that
 * does not match publish (publish uses the completed payload after the visual
 * builder fills `interval`).
 */
const triggerFormSchemaBase = z.object({
  name: z.string().optional(),
  triggerType: z.string(),
  scheduleType: z.string().optional(),
  interval: z.string().optional(),
  cron: z.string().max(256).optional(),
  timezone: z.string().optional(),
  missedSchedulePolicy: z
    .enum([
      MissedSchedulePolicyEnum.SKIP,
      MissedSchedulePolicyEnum.BUFFER_ONE,
      MissedSchedulePolicyEnum.BUFFER_ALL,
      MissedSchedulePolicyEnum.ALLOW_ALL,
      MissedSchedulePolicyEnum.CANCEL_OTHER,
    ])
    .optional(),
  inputSchema: z.string().optional(),
  outputSchema: z.string().optional(),
  outputFields: z.array(subWorkflowOutputFieldSchema).optional(),
  outputMapping: z.record(z.string(), z.string()).optional(),
  triggerId: z.string().optional(),
  triggerIndex: z.number().optional(),
  webhookPath: z.string().optional(),
  authorizedServiceAccountIds: z.array(z.string().uuid()).optional(),
})

function validateInputSchemaJson(schemaText: string | undefined, ctx: z.RefinementCtx) {
  const trimmed = schemaText?.trim() ?? ''
  if (!trimmed) return

  if (trimmed.length > 100_000) {
    ctx.addIssue({ code: z.ZodIssueCode.custom, message: 'Input schema must be 100KB or less', path: ['inputSchema'] })
    return
  }
  try {
    const parsed: unknown = JSON.parse(trimmed, safeJSONReviver)
    if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: 'Input schema must be a JSON object',
        path: ['inputSchema'],
      })
    }
  } catch {
    ctx.addIssue({ code: z.ZodIssueCode.custom, message: 'Invalid JSON — check syntax', path: ['inputSchema'] })
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function parseOutputSchemaJson(text: string, ctx: z.RefinementCtx): Record<string, unknown> | undefined {
  if (text.length > 100_000) {
    ctx.addIssue({
      code: z.ZodIssueCode.custom,
      message: 'Output schema must be 100KB or less',
      path: ['outputSchema'],
    })
    return undefined
  }
  let parsed: unknown
  try {
    parsed = JSON.parse(text, safeJSONReviver) as unknown
  } catch {
    ctx.addIssue({ code: z.ZodIssueCode.custom, message: 'Invalid JSON — check syntax', path: ['outputSchema'] })
    return undefined
  }
  if (!isRecord(parsed) || !isRecord(parsed['properties'])) {
    ctx.addIssue({
      code: z.ZodIssueCode.custom,
      message: 'Output schema must define an object with properties',
      path: ['outputSchema'],
    })
    return undefined
  }
  return parsed
}

function getOutputSchemaPaths(schema: Record<string, unknown>) {
  const paths = new Set<string>()
  const requiredPaths = new Set<string>()
  const visit = (current: Record<string, unknown>, prefix: string[] = [], requiredAncestors = true) => {
    if (!isRecord(current['properties'])) return
    const requiredNames = new Set(
      Array.isArray(current['required'])
        ? current['required'].filter((name): name is string => typeof name === 'string')
        : []
    )
    for (const [name, rawProperty] of Object.entries(current['properties'])) {
      if (!isRecord(rawProperty)) continue
      const fieldPath = [...prefix, name]
      const path = fieldPath.join('.')
      paths.add(path)
      const isRequired = requiredAncestors && requiredNames.has(name)
      if (isRequired) requiredPaths.add(path)
      visit(rawProperty, fieldPath, isRequired)
    }
  }
  visit(schema)
  return { paths, requiredPaths }
}

function validateOutputMappings(
  outputMapping: Record<string, string>,
  paths: Set<string>,
  requiredPaths: Set<string>,
  ctx: z.RefinementCtx
) {
  for (const [path, expression] of Object.entries(outputMapping)) {
    if (!paths.has(path)) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: `Mapping path "${path}" is not declared in the output schema`,
        path: ['outputMapping', path],
      })
    } else if (!/^\$\{[^{}]+\}$/.test(expression.trim())) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: 'Mapping value must be a template expression such as ${step.field}',
        path: ['outputMapping', path],
      })
    }
  }
  const mappedPaths = Object.keys(outputMapping)
  for (const path of requiredPaths) {
    const hasMapping = mappedPaths.some((mappedPath) => path === mappedPath || path.startsWith(`${mappedPath}.`))
    if (!hasMapping) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: `Required output "${path}" needs a mapping`,
        path: ['outputMapping', path],
      })
    }
  }
}

function validateSimpleOutputNames(data: z.infer<typeof triggerFormSchemaBase>, ctx: z.RefinementCtx) {
  if (data.triggerType !== TriggerTypeEnum.SUBWORKFLOW_TRIGGER) return
  const allowedSegment = /^[a-zA-Z0-9_ -]+$/
  const seenPaths = new Set<string>()
  for (const [index, field] of (data.outputFields ?? []).entries()) {
    const segments = field.path.split('.').map((segment) => segment.trim())
    const path = segments.join('.')
    if (!path) continue
    if (segments.some((segment) => !segment || !allowedSegment.test(segment))) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: 'Use letters, numbers, spaces, underscores, or hyphens in each field name.',
        path: ['outputFields', index, 'path'],
      })
    }
    if (
      seenPaths.has(path) ||
      [...seenPaths].some((seenPath) => seenPath.startsWith(`${path}.`) || path.startsWith(`${seenPath}.`))
    ) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: 'Output names must be unique and cannot overlap a parent object path.',
        path: ['outputFields', index, 'path'],
      })
    }
    seenPaths.add(path)
  }
}

function validateOutputContract(data: z.infer<typeof triggerFormSchemaBase>, ctx: z.RefinementCtx) {
  if (data.triggerType !== TriggerTypeEnum.SUBWORKFLOW_TRIGGER) return
  const text = data.outputSchema?.trim() ?? ''
  const outputMapping = data.outputMapping ?? {}
  if (!text) {
    if (Object.keys(outputMapping).length > 0) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: 'Output mappings require an output schema',
        path: ['outputMapping'],
      })
    }
    return
  }
  const schema = parseOutputSchemaJson(text, ctx)
  if (!schema) return
  const { paths, requiredPaths } = getOutputSchemaPaths(schema)
  validateOutputMappings(outputMapping, paths, requiredPaths, ctx)
}

function validateWebhookPathFormat(webhookPath: string | undefined, ctx: z.RefinementCtx) {
  const trimmed = webhookPath?.trim() ?? ''
  const normalized = trimmed.replace(/^\/+/, '').toLowerCase()
  if (!normalized) return

  if (normalized.length > 128) {
    ctx.addIssue({
      code: z.ZodIssueCode.custom,
      message: 'Webhook path must be 128 characters or fewer',
      path: ['webhookPath'],
    })
    return
  }
  if (!isValidWebhookPath(normalized)) {
    ctx.addIssue({
      code: z.ZodIssueCode.custom,
      message:
        'Path must start and end with a letter or number, and contain only lowercase letters, numbers, hyphens, and underscores',
      path: ['webhookPath'],
    })
  }
}

function validateScheduleInterval(data: z.infer<typeof triggerFormSchemaBase>, ctx: z.RefinementCtx) {
  const parsed = parseRepeatingInterval(data.interval ?? '')
  if (!parsed.start) return
  if (parsed.end && parsed.end < parsed.start) {
    ctx.addIssue({
      code: z.ZodIssueCode.custom,
      message: 'End date must be on or after the start date',
      path: ['interval'],
    })
  }
}

function validateCronFormat(cron: string | undefined, ctx: z.RefinementCtx) {
  const cronValue = cron?.trim() ?? ''
  if (!cronValue) return

  const fields = cronValue.split(/\s+/)
  if (fields.length !== 5) {
    ctx.addIssue({
      code: z.ZodIssueCode.custom,
      message: 'Cron expression must have exactly 5 fields: minute hour day-of-month month day-of-week',
      path: ['cron'],
    })
  } else if (!fields.every((f) => /^[\d*/,-]+$/.test(f))) {
    ctx.addIssue({
      code: z.ZodIssueCode.custom,
      message: 'Cron fields may only contain digits, *, /, -, and ,',
      path: ['cron'],
    })
  }
}

export const AUTHORIZED_SERVICE_ACCOUNT_REQUIRED_MESSAGE = 'At least one authorized service account is required'

export const triggerFormSchema = triggerFormSchemaBase.superRefine((data, ctx) => {
  if (
    data.triggerType === TriggerTypeEnum.MANUAL_TRIGGER ||
    data.triggerType === TriggerTypeEnum.SUBWORKFLOW_TRIGGER ||
    WEBHOOK_TRIGGER_TYPES.has(data.triggerType)
  ) {
    validateInputSchemaJson(data.inputSchema, ctx)
  }
  validateSimpleOutputNames(data, ctx)
  validateOutputContract(data, ctx)

  if (data.triggerType === TriggerTypeEnum.SCHEDULED && data.scheduleType === ScheduleTypeEnum.INTERVAL) {
    if (!data.interval?.trim()) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: 'A schedule is required',
        path: ['interval'],
      })
    } else {
      validateScheduleInterval(data, ctx)
    }
  }

  if (data.triggerType === TriggerTypeEnum.SCHEDULED && data.scheduleType === ScheduleTypeEnum.CRON) {
    if (!data.cron?.trim()) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: 'Cron expression is required',
        path: ['cron'],
      })
    } else {
      validateCronFormat(data.cron, ctx)
    }
  }

  if (WEBHOOK_TRIGGER_TYPES.has(data.triggerType)) {
    validateWebhookPathFormat(data.webhookPath, ctx)
    if (!data.authorizedServiceAccountIds?.length) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: AUTHORIZED_SERVICE_ACCOUNT_REQUIRED_MESSAGE,
        path: ['authorizedServiceAccountIds'],
      })
    }
  }
})

export type TriggerFormData = z.infer<typeof triggerFormSchemaBase>

// Re-export webhook path utilities from their canonical location
export { normalizeWebhookPath, isValidWebhookPath } from '../../../utils/webhookPath'

/** Download filename shared by webhook and EDA JSON schema fields. */
export const JSON_SCHEMA_DOWNLOAD_FILENAME = 'json-schema.json'

/** Default permissive JSON Schema used by webhook and EDA triggers. */
export const DEFAULT_JSON_SCHEMA = `{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "properties": {},
  "additionalProperties": true
}`

/** Example JSON Schema shown by webhook and EDA triggers. */
export const EXAMPLE_JSON_SCHEMA = JSON.stringify(
  {
    $schema: 'http://json-schema.org/draft-07/schema#',
    type: 'object',
    properties: {
      event: { type: 'string' },
      payload: { type: 'object' },
    },
    required: ['event'],
    additionalProperties: false,
  },
  null,
  2
)
