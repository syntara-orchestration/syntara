import { RuleTester } from 'eslint'
import { describe, it } from 'vitest'
import rule from '../rules/no-hardcoded-doc-urls.js'

RuleTester.describe = describe
RuleTester.it = it

const ruleTester = new RuleTester({
  languageOptions: {
    ecmaVersion: 2022,
    sourceType: 'module',
    parserOptions: { ecmaFeatures: { jsx: true } },
  },
})

ruleTester.run('no-hardcoded-doc-urls', rule, {
  valid: [
    // Non-doc URL string literals are allowed
    {
      code: `const url = 'https://github.com/foo/bar';`,
    },
    // Empty strings are allowed
    {
      code: `const empty = '';`,
    },
    // useDocLink hook call is the correct pattern — no literal URL present
    {
      code: `
        import { useDocLink } from '../../utils/docs/useDocLink';
        function WorkflowsPage() {
          const docLink = useDocLink('workflows');
          return docLink;
        }
      `,
    },
    // Relative URLs are allowed (not doc URLs)
    {
      code: `const path = '/docs/getting-started';`,
    },
    // A string that CONTAINS a doc prefix but does not START with it is allowed
    // (rule uses startsWith, not includes)
    {
      code: `const msg = 'See https://docs.ansible.com for details';`,
    },
    // JSX component consuming a useDocLink result — no hardcoded URL literal
    {
      code: `
        import { useDocLink } from '../../utils/docs/useDocLink';
        import { SynPageHeader } from '../../components';
        function WorkflowsPage() {
          const docLink = useDocLink('workflows');
          return <SynPageHeader title="Workflows" docLink={docLink} />;
        }
      `,
    },
    // A URL that starts with 'https://docs' but NOT with any guarded prefix
    {
      code: `const link = 'https://docs.example.com/en/guide/introduction';`,
    },
    // docsUrls.json is an exempt file — hardcoded URLs are allowed there.
    // RuleTester parses code as JS, so we represent the JSON content as a JS
    // object expression to exercise the filename-based exemption logic.
    {
      code: `
        const urls = {
          workflows: {
            upstream: 'https://docs.ansible.com/ansible-automation-platform/latest/',
            docs: 'https://docs.redhat.com/en/documentation/ansible-automation-platform/',
          },
        };
      `,
      filename: 'src/utils/docs/docsUrls.json',
    },
    // useDocLink.ts is an exempt file — it reads the registry, so URLs appear there
    {
      code: `
        import docsUrls from './docsUrls.json';
        const base = 'https://docs.ansible.com/';
        export function useDocLink(key) {
          return docsUrls[key];
        }
      `,
      filename: 'src/utils/docs/useDocLink.ts',
    },
    // *.test.ts files are exempt — tests may assert on URL values
    {
      code: `
        import { expect } from 'vitest';
        expect(docLink).toBe('https://docs.redhat.com/en/documentation/ansible-automation-platform/');
      `,
      filename: 'src/utils/docs/useDocLink.test.ts',
    },
    // *.spec.tsx files are exempt — E2E / integration specs may hardcode URLs
    {
      code: `
        const expectedUrl = 'https://docs.ansible.com/ansible/latest/user_guide/';
      `,
      filename: 'src/pages/workflows/Workflows.spec.tsx',
    },
  ],
  invalid: [
    // Hardcoded access.redhat.com/documentation/ URL in a variable assignment
    {
      code: `
        const docUrl = 'https://access.redhat.com/documentation/ansible-automation-platform/';
      `,
      errors: [{ messageId: 'noHardcodedDocUrl' }],
    },
    // Hardcoded docs.redhat.com/ URL as a JSX prop value
    {
      code: `
        import { Button } from '@patternfly/react-core';
        const App = () => (
          <Button
            component="a"
            href="https://docs.redhat.com/en/documentation/ansible-automation-platform/"
          >
            Documentation
          </Button>
        );
      `,
      errors: [{ messageId: 'noHardcodedDocUrl' }],
    },
    // Hardcoded docs.ansible.com/ URL as a function argument
    {
      code: `
        import { openExternalLink } from '../../utils/links';
        function handleClick() {
          openExternalLink('https://docs.ansible.com/ansible/latest/user_guide/');
        }
      `,
      errors: [{ messageId: 'noHardcodedDocUrl' }],
    },
    // Hardcoded ansible.readthedocs.io/ URL in an object property
    {
      code: `
        const pageConfig = {
          title: 'Execution Environments',
          docUrl: 'https://ansible.readthedocs.io/projects/builder/en/latest/',
        };
      `,
      errors: [{ messageId: 'noHardcodedDocUrl' }],
    },
    // Hardcoded docs.ansible.com/ URL in a JSX href prop on an anchor element
    {
      code: `
        const HelpLink = () => (
          <a
            href="https://docs.ansible.com/ansible-automation-platform/latest/"
            target="_blank"
            rel="noreferrer"
          >
            Learn more
          </a>
        );
      `,
      errors: [{ messageId: 'noHardcodedDocUrl' }],
    },
    // Hardcoded docs.redhat.com/ URL exported as a named constant
    {
      code: `
        export const WORKFLOWS_DOC_URL = 'https://docs.redhat.com/en/documentation/ansible-automation-platform/latest/html/using_automation_execution/';
      `,
      errors: [{ messageId: 'noHardcodedDocUrl' }],
    },
    // Fully static template literal with a doc URL prefix is also caught
    {
      code: 'const url = `https://docs.ansible.com/ansible/latest/`',
      errors: [{ messageId: 'noHardcodedDocUrl' }],
    },
  ],
})
