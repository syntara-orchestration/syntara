import ansiblePlugin from '@ansible/eslint-plugin'
import { RuleTester } from 'eslint'
import { describe, expect, it } from 'vitest'
import rule from '../rules/require-http-client-disable-reason.js'

RuleTester.describe = describe
RuleTester.it = it

const ruleTester = new RuleTester({
  languageOptions: {
    ecmaVersion: 2022,
    sourceType: 'module',
  },
  plugins: { '@ansible': ansiblePlugin },
})

ruleTester.run('require-http-client-disable-reason', rule, {
  valid: [
    { code: 'const request = () => undefined' },
    { code: '// eslint-disable-next-line no-console\nconsole.log("auth flow")' },
    { code: '// eslint-enable @ansible/no-unapproved-http-client\nconst request = () => undefined' },
    {
      code: '// eslint-disable-next-line @ansible/no-unapproved-http-client -- auth exchange before client initialization\nfetch("/api/v1/auth/token")',
    },
    {
      code: 'fetch("/api/v1/auth/token") // eslint-disable-line @ansible/no-unapproved-http-client -- auth exchange before client initialization',
    },
    {
      code: '/* eslint-disable no-console, @ansible/no-unapproved-http-client -- auth exchange before client initialization */\nconst request = () => undefined',
    },
    {
      code: '/* eslint-disable\n@ansible/no-unapproved-http-client -- auth exchange before client initialization\n*/\nconst request = () => undefined',
    },
    {
      code: '/* eslint-disable -- temporary all-rule exception with a reason */\nconst request = () => undefined',
    },
  ],
  invalid: [
    {
      code: '// eslint-disable-next-line @ansible/no-unapproved-http-client\nfetch("/api/v1/auth/token")',
      errors: [{ messageId: 'missingReason' }],
    },
    {
      code: 'fetch("/api/v1/auth/token") // eslint-disable-line @ansible/no-unapproved-http-client',
      errors: [{ messageId: 'missingReason' }],
    },
    {
      code: '/* eslint-disable no-console, @ansible/no-unapproved-http-client */\nconst request = () => undefined',
      errors: [{ messageId: 'missingReason' }],
    },
    {
      code: '/* eslint-disable\n@ansible/no-unapproved-http-client\n*/\nconst request = () => undefined',
      errors: [{ messageId: 'missingReason' }],
    },
    {
      code: '// eslint-disable-next-line @ansible/no-unapproved-http-client --   \nfetch("/api/v1/auth/token")',
      errors: [{ messageId: 'missingReason' }],
    },
  ],
})
