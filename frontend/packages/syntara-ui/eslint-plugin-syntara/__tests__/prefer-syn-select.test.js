import { RuleTester } from 'eslint'
import { describe, it } from 'vitest'
import rule from '../rules/prefer-syn-select.js'

RuleTester.describe = describe
RuleTester.it = it

const ruleTester = new RuleTester({
  languageOptions: {
    ecmaVersion: 2022,
    sourceType: 'module',
    parserOptions: { ecmaFeatures: { jsx: true } },
  },
})

ruleTester.run('prefer-syn-select', rule, {
  valid: [
    {
      code: `
        import { SynSelect } from '../components/SynSelect';
        const App = () => <SynSelect isOpen={false} onOpenChange={() => undefined} />;
      `,
    },
    {
      code: `
        import { SelectList, SelectOption, MenuToggle } from '@patternfly/react-core';
        const App = () => (
          <SelectList>
            <SelectOption value="one">One</SelectOption>
          </SelectList>
        );
      `,
    },
    {
      code: `import { Select } from '@patternfly/react-core';`,
      filename: '/src/components/SynSelect.tsx',
    },
    {
      code: `import { Select as PfSelect } from 'some-other-library';`,
    },
  ],
  invalid: [
    {
      code: `import { Select } from '@patternfly/react-core';`,
      errors: [{ messageId: 'preferSynSelect' }],
    },
    {
      code: `import { Select, SelectList } from '@patternfly/react-core';`,
      errors: [{ messageId: 'preferSynSelect' }],
    },
    {
      code: `import { Select as PfSelect } from '@patternfly/react-core';`,
      errors: [{ messageId: 'preferSynSelect' }],
    },
    {
      code: `import { Select } from '@patternfly/react-core';`,
      filename: '/src/routes/example/MyForm.tsx',
      errors: [{ messageId: 'preferSynSelect' }],
    },
  ],
})
