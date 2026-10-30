import { MissedSchedulePolicyEnum, ScheduleTypeEnum, TriggerTypeEnum, WEBHOOK_TRIGGER_TYPES } from '@syntara/contracts'
import type { FormDefinition } from '@syntara/contracts'
import { z } from 'zod'

import { formDefinitionBuilderSchema } from '../../../forms'
import { safeJSONReviver } from '../../../utils/jsonSafeParse'
import { parseRepeatingInterval } from '../../../utils/triggerFormatting'
import { isValidWebhookPath } from '../../../utils/webhookPath'

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
  webhookPath: z.string().optional(),
  authorizedServiceAccountIds: z.array(z.string().uuid()).optional(),
  form_definition: formDefinitionBuilderSchema.optional(),
  message: z.string().max(2000).optional(),
  submit_label: z.string().max(64).optional(),
  success_message: z.string().max(500).optional(),
  css_override: z.string().max(10000).optional(),
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

type TriggerFormSchemaInput = z.infer<typeof triggerFormSchemaBase>

function refineScheduledTriggerForm(data: TriggerFormSchemaInput, ctx: z.RefinementCtx) {
  if (data.triggerType !== TriggerTypeEnum.SCHEDULED) return

  if (data.scheduleType === ScheduleTypeEnum.INTERVAL) {
    if (!data.interval?.trim()) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: 'A schedule is required',
        path: ['interval'],
      })
    } else {
      validateScheduleInterval(data, ctx)
    }
    return
  }

  if (data.scheduleType === ScheduleTypeEnum.CRON) {
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
}

function refineWebhookStyleTriggerForm(data: TriggerFormSchemaInput, ctx: z.RefinementCtx) {
  if (!WEBHOOK_TRIGGER_TYPES.has(data.triggerType)) return

  validateWebhookPathFormat(data.webhookPath, ctx)
  if (!data.authorizedServiceAccountIds?.length) {
    ctx.addIssue({
      code: z.ZodIssueCode.custom,
      message: AUTHORIZED_SERVICE_ACCOUNT_REQUIRED_MESSAGE,
      path: ['authorizedServiceAccountIds'],
    })
  }
}

function refineTriggerFormSchema(data: TriggerFormSchemaInput, ctx: z.RefinementCtx) {
  if (data.triggerType === TriggerTypeEnum.MANUAL_TRIGGER || WEBHOOK_TRIGGER_TYPES.has(data.triggerType)) {
    validateInputSchemaJson(data.inputSchema, ctx)
  }

  refineScheduledTriggerForm(data, ctx)
  refineWebhookStyleTriggerForm(data, ctx)
}

export type TriggerFormData = Omit<z.infer<typeof triggerFormSchemaBase>, 'form_definition'> & {
  form_definition?: FormDefinition
}

export const triggerFormSchema = triggerFormSchemaBase.superRefine(
  refineTriggerFormSchema
) as unknown as z.ZodType<TriggerFormData>

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
