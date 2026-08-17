import { RuleTester } from 'eslint'
import { describe, it } from 'vitest'
import rule from '../rules/no-locale-date-format.js'

RuleTester.describe = describe
RuleTester.it = it

const ruleTester = new RuleTester({
  languageOptions: {
    ecmaVersion: 2022,
    sourceType: 'module',
    parserOptions: { ecmaFeatures: { jsx: true } },
  },
})

const allowedFilesOption = [
  {
    allowedFiles: ['**/utils/dateUtils.ts', '**/components/table/DateCell.tsx'],
  },
]

ruleTester.run('no-locale-date-format', rule, {
  valid: [
    {
      code: `
        import { formatDateTime } from '../../utils/dateUtils';
        const d = formatDateTime(isoString);
      `,
    },
    {
      code: `
        import { DateCell } from '../../components/table/DateCell';
        const App = () => <DateCell dateString={iso} />;
      `,
    },
    {
      code: `
        import { Content } from '@patternfly/react-core';
        const App = () => <Content>Hello</Content>;
      `,
    },
    {
      code: `const n = someNumber.toLocaleString();`,
    },
    {
      code: `const s = someVar.toLocaleString();`,
    },
    // Canonical wrapper components (allowlisted) may import Timestamp directly.
    {
      code: `
        import { Timestamp } from '@patternfly/react-core';
        const App = () => <Timestamp date={d} />;
      `,
      filename: '/repo/src/components/table/DateCell.tsx',
      options: allowedFilesOption,
    },
    // dateUtils.ts (allowlisted) may use raw locale Date methods.
    {
      code: `const t = date.toLocaleTimeString('en-US', {});`,
      filename: '/repo/src/utils/dateUtils.ts',
      options: allowedFilesOption,
    },
  ],
  invalid: [
    {
      code: `const d = new Date(iso).toLocaleString();`,
      errors: [{ messageId: 'noLocaleDate' }],
    },
    {
      code: `const d = new Date().toLocaleString();`,
      errors: [{ messageId: 'noLocaleDate' }],
    },
    {
      code: `const d = date.toLocaleDateString();`,
      errors: [{ messageId: 'noLocaleDate' }],
    },
    {
      code: `const t = date.toLocaleTimeString('en-US', {});`,
      errors: [{ messageId: 'noLocaleDate' }],
    },
    {
      code: `
        import { Timestamp } from '@patternfly/react-core';
        const App = () => <Timestamp date={d} />;
      `,
      errors: [{ messageId: 'restrictedTimestampImport' }],
    },
    {
      code: `
        import { Content, Timestamp } from '@patternfly/react-core';
        const App = () => <Timestamp date={d} />;
      `,
      errors: [{ messageId: 'restrictedTimestampImport' }],
    },
    // Non-allowlisted file still flagged even when other files are allowlisted.
    {
      code: `
        import { Timestamp } from '@patternfly/react-core';
        const App = () => <Timestamp date={d} />;
      `,
      filename: '/repo/src/routes/workflows/WorkflowsTableBody.tsx',
      options: allowedFilesOption,
      errors: [{ messageId: 'restrictedTimestampImport' }],
    },
  ],
})
