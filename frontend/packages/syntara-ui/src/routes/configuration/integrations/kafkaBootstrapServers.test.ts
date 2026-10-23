import { describe, expect, it } from 'vitest'

import { bootstrapServersFieldError, formatBootstrapServers, parseBootstrapServers } from './kafkaBootstrapServers'

describe('parseBootstrapServers', () => {
  it('splits commas and newlines and drops blanks', () => {
    expect(parseBootstrapServers(' broker.example.com:9093 \nother.example.com:9092, ')).toEqual([
      'broker.example.com:9093',
      'other.example.com:9092',
    ])
  })
})

describe('formatBootstrapServers', () => {
  it('joins broker addresses with newlines', () => {
    expect(formatBootstrapServers(['broker.example.com:9093', 'other.example.com:9092'])).toBe(
      'broker.example.com:9093\nother.example.com:9092'
    )
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

  it('rejects a path, query, userinfo, or space in the address', () => {
    expect(bootstrapServersFieldError('broker.example.com:9093/topic')).toMatch(/no path, query, or userinfo/)
    expect(bootstrapServersFieldError('user@broker.example.com:9093')).toMatch(/no path, query, or userinfo/)
    expect(bootstrapServersFieldError('broker example.com:9093')).toMatch(/no path, query, or userinfo/)
  })

  it('rejects an ipv6 address that is not [ipv6]:port', () => {
    expect(bootstrapServersFieldError('[2001:db8::1]')).toMatch(/\[ipv6\]:port/)
    expect(bootstrapServersFieldError('[]:9092')).toMatch(/\[ipv6\]:port/)
  })

  it('rejects a missing host or a non-numeric port', () => {
    expect(bootstrapServersFieldError(':9093')).toMatch(/missing a host/)
    expect(bootstrapServersFieldError('broker.example.com:abc')).toMatch(/non-numeric port/)
    expect(bootstrapServersFieldError('broker.example.com:0')).toMatch(/1-65535/)
  })

  it('rejects more than 20 brokers', () => {
    const servers = Array.from({ length: 21 }, (_, index) => `broker-${String(index)}.example.com:9093`)
    expect(bootstrapServersFieldError(servers.join('\n'))).toBe('At most 20 bootstrap servers are allowed')
  })
})
