import { describe, expect, it } from 'vitest'

import { isUriReference } from './uriReference'

describe('URI-reference validation', () => {
  it.each([
    '',
    '/',
    '/workflows/order-completion',
    'orders/completed',
    '../orders',
    '?state=done',
    '#event',
    'urn:syntara:orders',
    'urn:',
    'mailto:events@example.com',
    'https://example.com:9093/orders?state=done#event',
    '//example.com/orders',
    '//',
    'https://user:password@example.com/orders',
    'https://[::1]/orders',
    'https://[2001:db8::1]:9093/orders',
    'https://[v1.future]/orders',
    '/orders%2Fcompleted',
  ])('accepts the RFC 3986 reference %s', (value) => {
    expect(isUriReference(value)).toBe(true)
  })

  it.each([
    'not a URI',
    '/orders\ncompleted',
    '/bad%escape',
    '1:invalid',
    ':invalid',
    'https://host:port/orders',
    'https://[invalid]/orders',
    'https://user@@host/orders',
    '/path[invalid]',
    '/orders?state[]=done',
    '/orders#first#second',
    '/orders/é',
    '/bad\\path',
    'https://[2001:db8:::1]/orders',
  ])('rejects the invalid reference %s', (value) => {
    expect(isUriReference(value)).toBe(false)
  })
})
