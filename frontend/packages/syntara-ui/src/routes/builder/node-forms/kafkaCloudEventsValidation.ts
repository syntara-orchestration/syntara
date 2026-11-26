import { isUriReference } from '../../../utils/uriReference'

const managedHeaders = new Set(['ce_type', 'ce_source', 'ce_specversion', 'ce_id', 'ce_time', 'content-type'])
const reservedHeaders = new Set(['ce_data', 'ce_datacontenttype', 'ce_extensions'])
const templateExpression = /\$\{[^}]+\}/
export const KAFKA_CLOUDEVENTS_HEADER_COUNT = managedHeaders.size

export function isCloudEventsText(value: string): boolean {
  for (const character of value) {
    const point = character.codePointAt(0) ?? 0
    if (
      point <= 0x1f ||
      (point >= 0x7f && point <= 0x9f) ||
      (point >= 0xd800 && point <= 0xdfff) ||
      (point >= 0xfdd0 && point <= 0xfdef) ||
      (point & 0xffff) >= 0xfffe
    )
      return false
  }
  return true
}

export function isCloudEventsSource(value: string): boolean {
  return value.length > 0 && isCloudEventsText(value) && (templateExpression.test(value) || isUriReference(value))
}

type HeaderInput = { name: string; encoding: 'null' | 'utf-8' | 'base64'; value: string }
type HeaderIssue = { field: 'name' | 'encoding' | 'value'; message: string }

function attributeValue(header: HeaderInput): string {
  if (header.encoding !== 'base64') return header.value
  const bytes = Uint8Array.from(atob(header.value), (character) => character.charCodeAt(0))
  return new TextDecoder('utf-8', { fatal: true, ignoreBOM: true }).decode(bytes)
}

export function cloudEventsHeaderIssue(header: HeaderInput, names: Set<string>): HeaderIssue | undefined {
  if (templateExpression.test(header.name)) return undefined
  const name = header.name.toLowerCase()
  if (managedHeaders.has(name))
    return { field: 'name', message: 'This header is managed automatically in CloudEvents mode' }
  if (!name.startsWith('ce_')) return undefined
  if (!/^ce_[a-z0-9]+$/.test(header.name) || reservedHeaders.has(name))
    return { field: 'name', message: 'Use an available CloudEvents attribute name with lowercase letters and digits' }
  if (names.has(name)) return { field: 'name', message: 'CloudEvents attribute headers must be unique' }
  names.add(name)
  if (header.encoding === 'null')
    return { field: 'encoding', message: 'CloudEvents attributes require a UTF-8 text value' }
  if (templateExpression.test(header.value)) return undefined
  try {
    const value = attributeValue(header)
    if (isCloudEventsText(value)) return undefined
  } catch {
    return { field: 'value', message: 'CloudEvents attributes require valid UTF-8 text without control characters' }
  }
  return { field: 'value', message: 'CloudEvents attributes require valid UTF-8 text without control characters' }
}
