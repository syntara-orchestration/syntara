import { describe, expect, it } from 'vitest'

import { bootstrapServersFieldError, parseBootstrapServers } from './kafkaBootstrapServers'

describe('parseBootstrapServers', () => {
  it('splits commas and newlines and drops blanks', () => {
    expect(parseBootstrapServers(' broker.example.com:9093 \nother.example.com:9092, ')).toEqual([
      'broker.example.com:9093',
      'other.example.com:9092',
    ])
  })
})

describe('bootstrapServersFieldError', () => {
  it('accepts host:port and bracketed ipv6', () => {
    expect(bootstrapServersFieldError('broker.example.com:9093\n[2001:db8::1]:9092')).toBeUndefined()
  })

  it('rejects an empty list, a missing port, and a private-looking but malformed address', () => {
    expect(bootstrapServersFieldError('   ')).toBe('At least one bootstrap server is required')
    expect(bootstrapServersFieldError('broker.example.com')).toMatch(/host:port/)
    expect(bootstrapServersFieldError('broker.example.com:70000')).toMatch(/1-65535/)
  })
})
