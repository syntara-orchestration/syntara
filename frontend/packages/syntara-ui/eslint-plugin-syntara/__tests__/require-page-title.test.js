import { RuleTester } from 'eslint'
import { describe, it } from 'vitest'
import rule from '../rules/require-page-title.js'

RuleTester.describe = describe
RuleTester.it = it

const ruleTester = new RuleTester({
  languageOptions: {
    ecmaVersion: 2022,
    sourceType: 'module',
    parserOptions: {
      ecmaFeatures: { jsx: true },
    },
  },
})

ruleTester.run('syntara/require-page-title', rule, {
  valid: [
    // Page component using SynPageTitle — preferred pattern
    {
      code: `
        export default function MyPage() {
          return (
            <SynPage>
              <SynPageTitle segments={['My Page']} />
              <SynPageHeader title="My Page" />
            </SynPage>
          )
        }
      `,
    },
    // Page component with a raw <title> element — also accepted
    {
      code: `
        export default function MyPage() {
          return (
            <div>
              <title>My Page | Syntara</title>
              <h1>My Page</h1>
            </div>
          )
        }
      `,
    },
    // <title> nested inside another element — still counts
    {
      code: `
        export default function MyPage() {
          return (
            <SynPage>
              <title>{toPageTitle(['My Page'])}</title>
              <SynPageHeader title="My Page" />
            </SynPage>
          )
        }
      `,
    },
    // Not a page component (no default export) — rule does not apply
    {
      code: `
        export function HelperComponent() {
          return <div><p>Helper</p></div>
        }
      `,
    },
    // File with no exports at all — rule does not apply
    {
      code: `
        function internalHelper() {
          return null
        }
      `,
    },
  ],
  invalid: [
    // Default-exported page component missing SynPageTitle or <title>
    {
      code: `
        export default function MyPage() {
          return (
            <div>
              <h1>My Page</h1>
            </div>
          )
        }
      `,
      errors: [{ messageId: 'missingTitle' }],
    },
    // Arrow function default export without SynPageTitle or <title>
    {
      code: `
        const MyPage = () => (
          <div>
            <SynPageHeader title="My Page" />
          </div>
        )
        export default MyPage
      `,
      errors: [{ messageId: 'missingTitle' }],
    },
  ],
})
