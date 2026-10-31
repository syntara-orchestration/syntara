import type { WorkflowAPI } from '@syntara/contracts'
import { z } from 'zod'

import { nodeSettingsSchema } from './shared/nodeSettingsSchema'

const fullTemplate = /^\$\{[\s\S]+\}$/
const encodedValue = z.strictObject({ encoding: z.enum(['utf-8', 'base64']), value: z.string() })
const header = z.strictObject({ name: z.string(), value: encodedValue.nullable() })
const headers = z.union([z.array(header).max(128), z.string().regex(fullTemplate)])

function parseJsonOrTemplate(text: string): unknown {
  const trimmed = text.trim()
  if (fullTemplate.test(trimmed)) return trimmed
  return JSON.parse(trimmed) as unknown
}

function validJson(text: string): boolean {
  try {
    return z.json().safeParse(parseJsonOrTemplate(text)).success
  } catch {
    return false
  }
}

function validKey(text: string): boolean {
  if (!text.trim()) return true
  try {
    return encodedValue.nullable().safeParse(parseJsonOrTemplate(text)).success
  } catch {
    return false
  }
}

function validHeaders(text: string): boolean {
  if (!text.trim()) return true
  try {
    return headers.safeParse(parseJsonOrTemplate(text)).success
  } catch {
    return false
  }
}

export const kafkaPublishFormSchema = z.object({
  name: z.string(),
  integration_id: z.uuid('Select a Kafka integration'),
  credential_id: z.union([z.uuid(), z.literal('')]),
  topic: z
    .string()
    .min(1)
    .max(249)
    .regex(/^[a-zA-Z0-9._-]+$/, 'Enter one literal Kafka topic name')
    .refine((value) => value !== '.' && value !== '..', 'Enter one literal Kafka topic name'),
  payload: z.string().min(1, 'Enter a JSON payload').refine(validJson, 'Enter valid JSON or a full-value template'),
  key: z.string().refine(validKey, 'Use null or an encoding/value object'),
  headers: z.string().refine(validHeaders, 'Use an ordered header list or a full-value template; at most 128 entries'),
  settings: nodeSettingsSchema,
})

export type KafkaPublishFormData = z.infer<typeof kafkaPublishFormSchema>

export function buildKafkaPublishParameters(
  data: KafkaPublishFormData
): WorkflowAPI.components['schemas']['KafkaPublishParameters'] {
  return {
    integration_id: data.integration_id,
    credential_id: data.credential_id || null,
    topic: data.topic,
    payload: parseJsonOrTemplate(data.payload),
    key: data.key.trim() ? encodedValue.nullable().parse(parseJsonOrTemplate(data.key)) : null,
    headers: data.headers.trim() ? headers.parse(parseJsonOrTemplate(data.headers)) : [],
  }
}
