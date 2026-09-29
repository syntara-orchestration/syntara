/** Vendor extension on JSON Schema properties for round-tripping dynamic option sources. */
export const SYNTARA_FORM_OPTIONS_EXTENSION = 'x-syntara-form-options' as const

export type SyntaraFormOptionsExtension = {
  source: 'dynamic'
  expression: string
  label_key?: string | null
  value_key?: string | null
}
