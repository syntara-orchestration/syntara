import { RuleTester } from 'eslint'
import { describe, it } from 'vitest'
import rule from '../rules/no-fetch-aliases.js'

RuleTester.describe = describe
RuleTester.it = it

const ruleTester = new RuleTester({
  languageOptions: {
    ecmaVersion: 2022,
    sourceType: 'module',
  },
})

ruleTester.run('no-fetch-aliases', rule, {
  valid: [
    { code: "fetch('/api/v1/workflows')" },
    { code: "window.fetch('/api/v1/workflows')" },
    { code: "globalThis['fetch']('/api/v1/workflows')" },
    { code: 'const request = client.fetch' },
    { code: 'const client = { fetch() {} }' },
    { code: 'class Client { fetch() {} }' },
    { code: 'class Client { fetch = () => undefined }' },
    { code: 'const { fetch } = client' },
    { code: 'function makeRequest(fetch) { return fetch }' },
    { code: 'function makeRequest(window) { return window.fetch }' },
    { code: 'function makeRequest(globalThis) { return globalThis.fetch }' },
  ],
  invalid: [
    {
      code: 'const request = fetch',
      errors: [{ messageId: 'noFetchAlias' }],
    },
    {
      code: 'registerFetch(fetch)',
      errors: [{ messageId: 'noFetchAlias' }],
    },
    {
      code: 'const request = window.fetch',
      errors: [{ messageId: 'noFetchAlias' }],
    },
    {
      code: "const request = globalThis['fetch']",
      errors: [{ messageId: 'noFetchAlias' }],
    },
    {
      code: 'registerFetch(window.fetch)',
      errors: [{ messageId: 'noFetchAlias' }],
    },
    {
      code: 'const { fetch: request } = window',
      errors: [{ messageId: 'noFetchAlias' }],
    },
    {
      code: "const { ['fetch']: request } = globalThis",
      errors: [{ messageId: 'noFetchAlias' }],
    },
    {
      code: 'let request; ({ fetch: request } = window)',
      errors: [{ messageId: 'noFetchAlias' }],
    },
  ],
})
