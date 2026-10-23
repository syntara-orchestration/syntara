export const KAFKA_SASL_MECHANISMS = [
  { value: 'SCRAM-SHA-256', label: 'SCRAM-SHA-256' },
  { value: 'SCRAM-SHA-512', label: 'SCRAM-SHA-512' },
  { value: 'PLAIN', label: 'PLAIN' },
] as const

export const DEFAULT_KAFKA_SASL_MECHANISM = 'SCRAM-SHA-256'

export type KafkaSaslMechanism = (typeof KAFKA_SASL_MECHANISMS)[number]['value']
