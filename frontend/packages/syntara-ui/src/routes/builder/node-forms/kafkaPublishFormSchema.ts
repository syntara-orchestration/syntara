import type { WorkflowAPI } from '@syntara/contracts'
import { z } from 'zod'

import type { ActivityMetadata } from '../../../stores/workflowStoreTypes'

import { nodeSettingsSchema } from './shared/nodeSettingsSchema'

export const KAFKA_MAX_HEADERS = 128
const fullTemplate = /^\$\{[\s\S]+\}$/
const templateExpression = /\$\{[^}]+\}/
const resourceUuid = /^[a-f\d]{8}-[a-f\d]{4}-[a-f\d]{4}-[a-f\d]{4}-[a-f\d]{12}$/i
const reference = z.string().regex(resourceUuid, 'Use a literal resource UUID')
const encodedValue = z.strictObject({ encoding: z.enum(['utf-8', 'base64']), value: z.string() })
const header = z.strictObject({ name: z.string(), value: encodedValue.nullable() })

/** Check saved value structures against the generated contract, allowing incomplete draft destinations to be edited. */
export const kafkaPublishParametersSchema = z
  .strictObject({
    integration_id: z
      .string()
      .nullish()
      .transform((value) => value ?? ''),
    // Drafts can omit a selection; executable workflow validation still requires a UUID.
    credential_id: z
      .string()
      .nullish()
      .transform((value) => value ?? ''),
    topic: z.string().default(''),
    payload: z.unknown().optional(),
    key: encodedValue.nullable().optional(),
    headers: z.union([z.array(header), z.string()]).optional(),
  })
  .transform((parameters) => ({ ...parameters, payload: parameters.payload })) satisfies z.ZodType<
  WorkflowAPI.components['schemas']['KafkaPublishParameters']
>

const byteFields = z.object({ encoding: z.enum(['null', 'utf-8', 'base64']), value: z.string() })

export function isKafkaPublishPayloadTemplate(text: string): boolean {
  return fullTemplate.test(text.trim())
}

function parseJsonOrTemplate(text: string): unknown {
  const trimmed = text.trim()
  if (isKafkaPublishPayloadTemplate(trimmed)) return trimmed
  return JSON.parse(trimmed) as unknown
}

function parseDraftPayload(text: string): unknown {
  try {
    const payload = parseJsonOrTemplate(text)
    return z.json().safeParse(payload).success ? payload : undefined
  } catch {
    return undefined
  }
}

function validJson(text: string): boolean {
  return parseDraftPayload(text) !== undefined
}

function validBytes(value: z.infer<typeof byteFields>): boolean {
  return (
    value.encoding !== 'base64' || templateExpression.test(value.value) || z.base64().safeParse(value.value).success
  )
}

export const kafkaPublishFormSchema = z
  .object({
    name: z.string(),
    integration_id: reference.or(z.literal('')).refine((value) => value !== '', 'Select a Kafka integration'),
    credential_id: z
      .string({ error: 'Select a runtime Kafka credential' })
      .min(1, 'Select a runtime Kafka credential')
      .regex(resourceUuid, 'Use a literal resource UUID'),
    connection_ready: z.boolean(),
    topic: z
      .string()
      .min(1, 'Enter a topic')
      .max(249, 'Topic names can contain at most 249 characters')
      .regex(/^[a-zA-Z0-9._-]+$/, 'Enter one literal Kafka topic name')
      .refine((value) => value !== '.' && value !== '..', 'Enter one literal Kafka topic name'),
    payload: z.string().min(1, 'Enter a JSON payload').refine(validJson, 'Enter valid JSON or a full-value template'),
    key: byteFields,
    headers_mode: z.enum(['entries', 'template']),
    headers: z.array(z.object({ name: z.string(), ...byteFields.shape })),
    headers_template: z.string(),
    settings: nodeSettingsSchema,
  })
  .superRefine((data, ctx) => {
    if (data.integration_id && !data.connection_ready) {
      ctx.addIssue({
        code: 'custom',
        path: ['connection_ready'],
        message: 'Kafka connection settings are not available',
      })
    }
    if (!validBytes(data.key)) {
      ctx.addIssue({ code: 'custom', path: ['key', 'value'], message: 'Enter valid standard Base64 or a template' })
    }
    if (data.headers_mode === 'template') {
      if (!fullTemplate.test(data.headers_template.trim())) {
        ctx.addIssue({
          code: 'custom',
          path: ['headers_template'],
          message: 'Enter a full-value template, such as ${trigger.payload.headers}',
        })
      }
      return
    }
    if (data.headers.length > KAFKA_MAX_HEADERS) {
      ctx.addIssue({
        code: 'custom',
        path: ['headers'],
        message: 'Use at most 128 header entries, including duplicates and null values',
      })
    }
    data.headers.forEach((entry, index) => {
      if (!validBytes(entry)) {
        ctx.addIssue({
          code: 'custom',
          path: ['headers', index, 'value'],
          message: 'Enter valid standard Base64 or a template',
        })
      }
    })
  })

export type KafkaPublishFormData = z.infer<typeof kafkaPublishFormSchema>

function buildBytes(value: z.infer<typeof byteFields>): WorkflowAPI.components['schemas']['KafkaEncodedValue'] | null {
  return value.encoding === 'null' ? null : { encoding: value.encoding, value: value.value }
}

export function buildKafkaPublishParameters(
  data: KafkaPublishFormData
): WorkflowAPI.components['schemas']['KafkaPublishParameters'] {
  return {
    integration_id: data.integration_id,
    credential_id: data.credential_id,
    topic: data.topic,
    payload: parseDraftPayload(data.payload),
    key: buildBytes(data.key),
    headers:
      data.headers_mode === 'template'
        ? data.headers_template.trim()
        : data.headers.map((entry) => ({ name: entry.name, value: buildBytes(entry) })),
  }
}

/** Preserve invalid editor text without turning it into an executable JSON string. */
export function buildKafkaPublishDraft(data: KafkaPublishFormData, previousMetadata?: ActivityMetadata) {
  const parameters = buildKafkaPublishParameters(data)
  const metadata = { ...previousMetadata }
  delete metadata.__kafkaPublishPayloadDraft
  if (parameters.payload === undefined) metadata.__kafkaPublishPayloadDraft = data.payload
  return { parameters, metadata: Object.keys(metadata).length ? metadata : undefined }
}

export function kafkaPublishInitialFields(
  parameters: WorkflowAPI.components['schemas']['KafkaPublishParameters'],
  metadata?: ActivityMetadata
): Partial<KafkaPublishFormData> {
  return {
    integration_id: parameters.integration_id,
    credential_id: parameters.credential_id ?? '',
    topic: parameters.topic,
    payload:
      metadata?.__kafkaPublishPayloadDraft ??
      (typeof parameters.payload === 'string' && fullTemplate.test(parameters.payload)
        ? parameters.payload
        : (JSON.stringify(parameters.payload, null, 2) ?? '')),
    key: parameters.key ?? { encoding: 'null', value: '' },
    headers_mode: typeof parameters.headers === 'string' ? 'template' : 'entries',
    headers_template: typeof parameters.headers === 'string' ? parameters.headers : '',
    headers: Array.isArray(parameters.headers)
      ? parameters.headers.map((entry) => ({
          name: entry.name,
          ...(entry.value ?? { encoding: 'null' as const, value: '' }),
        }))
      : [],
  }
}
