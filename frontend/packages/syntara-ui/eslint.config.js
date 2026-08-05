import storybook from 'eslint-plugin-storybook'
import js from '@eslint/js'
import globals from 'globals'
import react from 'eslint-plugin-react'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import jsxA11y from 'eslint-plugin-jsx-a11y'
import importPlugin from 'eslint-plugin-import-x'
import noOnlyTests from 'eslint-plugin-no-only-tests'
import testingLibrary from 'eslint-plugin-testing-library'
import sonarjs from 'eslint-plugin-sonarjs'
import unicorn from 'eslint-plugin-unicorn'
import vitest from '@vitest/eslint-plugin'
import pluginQuery from '@tanstack/eslint-plugin-query'
import reactUseEffect from 'eslint-plugin-react-you-might-not-need-an-effect'
import tseslint from 'typescript-eslint'
import eslintConfigPrettier from 'eslint-config-prettier'
import syntaraPlugin from './eslint-plugin-syntara/index.js'
import { fileURLToPath } from 'node:url'
import { dirname } from 'node:path'

const __filename = fileURLToPath(import.meta.url)
const __dirname = dirname(__filename)

const TEST_FILES = ['**/*.test.{ts,tsx}', '**/*.spec.{ts,tsx}']
const E2E_FILES = ['e2e/**']

export default tseslint.config(
  {
    ignores: [
      'dist',
      'coverage/**',
      'playwright.config.ts',
      'test-results/**',
      'playwright-report/**',
      'scripts/**',
      'eslint-plugin-syntara/**',
    ],
  },
  js.configs.recommended,
  ...tseslint.configs.recommendedTypeChecked,
  ...pluginQuery.configs['flat/recommended'],
  // Align with Sonar typescript:S2245 / CWE-338: Math.random is not suitable for secrets, tokens, or crypto.
  // Use globalThis.crypto.getRandomValues(), crypto.randomUUID(), node:crypto.randomInt/randomBytes, or the uuid package.
  {
    files: ['**/*.{js,jsx,ts,tsx}'],
    rules: {
      'no-restricted-syntax': [
        'error',
        {
          selector:
            'CallExpression[callee.type="MemberExpression"][callee.object.name="Math"][callee.property.name="random"]',
          message:
            'Do not use Math.random() — it is not cryptographically secure. Use crypto.getRandomValues(), crypto.randomUUID(), node:crypto.randomInt/randomBytes, or the uuid package. If the value is strictly non-security (e.g. visual jitter), add an eslint-disable-next-line with a short justification.',
        },
        {
          selector: 'JSXOpeningElement[name.name="Switch"] JSXAttribute[name.name="isReversed"]',
          message:
            'Do not use isReversed on PatternFly <Switch>. The default layout (toggle left, label right) is the UX standard.',
        },
        {
          selector:
            'CallExpression[callee.name="showSuccess"][arguments.0.type="Literal"], CallExpression[callee.name="showSuccess"][arguments.0.type="TemplateLiteral"], CallExpression[callee.name="showError"][arguments.0.type="Literal"], CallExpression[callee.name="showError"][arguments.0.type="TemplateLiteral"], CallExpression[callee.name="showWarning"][arguments.0.type="Literal"], CallExpression[callee.name="showWarning"][arguments.0.type="TemplateLiteral"], CallExpression[callee.name="showInfo"][arguments.0.type="Literal"], CallExpression[callee.name="showInfo"][arguments.0.type="TemplateLiteral"]',
          message:
            'Pass an object { title, description? } to showSuccess/showError/showWarning/showInfo() instead of a positional string argument.',
        },
        {
          selector:
            'CallExpression[callee.name="useQueryState"][arguments.1.type="Literal"], CallExpression[callee.name="useQueryState"][arguments.1.type="TemplateLiteral"]',
          message:
            'Pass an object { title, onRetry } to useQueryState instead of a plain string. The object form enables retry buttons in error states.',
        },
        {
          selector: 'MemberExpression[object.name="formState"][property.name="isSubmitting"]',
          message:
            'Do not use formState.isSubmitting -- it only covers the synchronous handleSubmit wrapper. Use isPending from the mutation hook (e.g. useMutation) to track the actual async mutation lifecycle.',
        },
        {
          selector: 'JSXOpeningElement[name.name="span"] JSXAttribute[name.name="aria-label"]',
          message:
            'Do not use aria-label on <span> — assistive technologies ignore it on non-interactive elements. The inner text content is sufficient. Use aria-label only on interactive elements, widgets, landmarks, images, or iframes.',
        },
        {
          selector:
            'ImportDeclaration[source.value=/routing\\/(useNavigate|useParams|useSearch|useLocation|navigate|Link)$/]',
          message: 'Deprecated bridge hook. Use @tanstack/react-router primitives directly.',
        },
        {
          selector:
            'ImportDeclaration[source.value="@patternfly/react-core"] > ImportSpecifier[imported.name="FormSelect"]',
          message:
            'Use PatternFly Select, SelectList, SelectOption, and MenuToggle instead of FormSelect / FormSelectOption.',
        },
        {
          selector:
            'ImportDeclaration[source.value="@patternfly/react-core"] > ImportSpecifier[imported.name="FormSelectOption"]',
          message:
            'Use PatternFly Select, SelectList, SelectOption, and MenuToggle instead of FormSelect / FormSelectOption.',
        },
      ],
      // axios restriction merged into the icon/wouter no-restricted-imports block below
      // to avoid flat-config rule shadowing (the last matching block wins for a given rule).
      // Raw HTTP calls are handled by syntara/no-raw-http-calls (fetch, XMLHttpRequest) below
      'no-restricted-properties': [
        'error',
        {
          object: 'crypto',
          property: 'randomUUID',
          message:
            'crypto.randomUUID is unavailable over HTTP (non-secure contexts). Use generateUUID() from src/utils/generateUUID.ts or React useId() for component keys.',
        },
      ],
    },
  },
  // Icon migration: flag non-RhUi icons at warn level (existing legacy imports being phased out incrementally).
  // Wouter ban and bridge hook deprecation use @typescript-eslint/no-restricted-imports (a separate
  // rule name) to avoid flat-config shadowing — two blocks setting the same rule on the same files
  // would cause the last one to win and silently drop the other.
  {
    files: ['**/*.{ts,tsx}'],
    ignores: [...TEST_FILES, ...E2E_FILES],
    rules: {
      'no-restricted-imports': [
        'warn',
        {
          patterns: [
            {
              group: ['@patternfly/react-icons'],
              importNamePattern: '^(?!RhUi)',
              message:
                'Use RhUi* icons from @patternfly/react-icons (e.g. RhUiAddIcon, RhUiTrashIcon, RhUiEditIcon). Non-RhUi icons are being phased out.',
            },
          ],
        },
      ],
    },
  },
  // Ban wouter (migration complete) and deprecate bridge hooks in favor of direct @tanstack/react-router imports.
  // useSearchParams is exempt — it is a supported utility, not a deprecated bridge.
  {
    files: ['**/*.{ts,tsx}'],
    ignores: ['**/hooks/routing/*.{ts,tsx}', '**/hooks/routing/*.test.{ts,tsx}'],
    rules: {
      '@typescript-eslint/no-restricted-imports': [
        'warn',
        {
          patterns: [
            {
              group: ['wouter', 'wouter/*'],
              message: 'wouter has been removed. Use @tanstack/react-router directly.',
            },
            {
              regex: '(?:\\.{1,2}/)*(?:hooks/)?routing/(?:useNavigate|useParams|useSearch|useLocation|navigate|Link)$',
              message: 'Deprecated bridge hook. Use @tanstack/react-router primitives directly.',
            },
            {
              group: ['@tanstack/react-router'],
              importNames: ['Link'],
              message:
                'Use NxLink from components/NxLink instead of TanStack Link directly. NxLink provides consistent PatternFly styling.',
            },
          ],
        },
      ],
    },
  },
  // NxLink.tsx wraps TanStack Link for general use. NxPageBreadcrumbs also
  // imports Link directly because NxLink renders a PF6 Button (wrong for breadcrumb styling).
  {
    files: ['**/components/NxLink.tsx', '**/components/layout/NxPageBreadcrumbs.tsx'],
    rules: {
      '@typescript-eslint/no-restricted-imports': 'off',
    },
  },
  {
    files: ['**/*.{ts,tsx}'],
    languageOptions: {
      ecmaVersion: 2020,
      globals: globals.browser,
      parserOptions: {
        project: ['./tsconfig.app.json', './tsconfig.node.json', './tsconfig.e2e.json', './tsconfig.storybook.json'],
        tsconfigRootDir: __dirname,
      },
    },
    settings: {
      react: { version: 'detect' },
    },
    plugins: {
      react,
      'react-hooks': reactHooks,
      'react-refresh': reactRefresh,
      'jsx-a11y': jsxA11y,
      'import-x': importPlugin,
      'no-only-tests': noOnlyTests,
      sonarjs,
      unicorn,
      syntara: syntaraPlugin,
      reactYouMightNotNeedAnEffect: reactUseEffect,
    },
    rules: {
      ...reactHooks.configs.recommended.rules,
      'react-hooks/exhaustive-deps': 'error',
      // Strict accessibility linting for JSX (labels, roles, alt text, etc.)
      ...jsxA11y.configs.strict.rules,
      // Allow tabIndex={0} on role="region" elements (e.g. NxScrollableTableContainer scroll region).
      // A named region landmark is the correct semantic wrapper when a non-interactive container needs
      // keyboard focus for scrolling (WCAG 2.1.1 / jsx-a11y/no-noninteractive-tabindex rule docs).
      'jsx-a11y/no-noninteractive-tabindex': ['error', { roles: ['region'] }],
      'react-refresh/only-export-components': ['error', { allowConstantExport: true }],
      eqeqeq: ['error', 'always', { null: 'ignore' }],
      // Disallow the `void` operator (Sonar S3735 / readability). For deliberately unawaited work from
      // sync callbacks, use `detachPromise(...)` (optionally `{ onReject }`); otherwise `await` or return
      // the promise so the caller handles errors. Do not confuse with TypeScript `: void` return types.
      'no-void': 'error',
      '@typescript-eslint/no-floating-promises': 'error',
      '@typescript-eslint/no-misused-promises': ['error', { checksVoidReturn: false }],
      '@typescript-eslint/no-explicit-any': 'error',
      '@typescript-eslint/no-unused-private-class-members': 'error',
      '@typescript-eslint/no-unnecessary-type-assertion': 'error',
      'no-console': 'error',
      'no-restricted-exports': ['error', { restrictDefaultExports: { direct: true } }],
      'no-only-tests/no-only-tests': 'error',
      'react/no-array-index-key': 'error',
      // Avoid new object/array identities as Context.Provider value (needless consumer rerenders; Sonar).
      'react/jsx-no-constructed-context-values': 'error',
      'react/jsx-no-useless-fragment': ['error', { allowExpressions: true }],
      'react/self-closing-comp': 'error',
      'unicorn/prefer-number-properties': 'error',
      'unicorn/consistent-template-literal-escape': 'error',
      'unicorn/no-useless-iterator-to-array': 'error',
      'unicorn/prefer-simple-condition-first': 'error',
      'unicorn/switch-case-break-position': 'error',
      '@typescript-eslint/prefer-optional-chain': 'error',
      '@typescript-eslint/prefer-nullish-coalescing': ['error', { ignorePrimitives: { string: true, boolean: true } }],
      '@typescript-eslint/require-array-sort-compare': 'error',
      '@typescript-eslint/switch-exhaustiveness-check': 'error',
      '@typescript-eslint/prefer-includes': 'error',
      // Type-checked rules from recommendedTypeChecked preset (adopted from AAP UI)
      '@typescript-eslint/no-unsafe-argument': 'error',
      '@typescript-eslint/no-unsafe-assignment': 'error',
      '@typescript-eslint/no-unsafe-call': 'error',
      '@typescript-eslint/no-unsafe-member-access': 'error',
      '@typescript-eslint/no-unsafe-return': 'error',
      '@typescript-eslint/await-thenable': 'error',
      '@typescript-eslint/require-await': 'error',
      '@typescript-eslint/unbound-method': 'error',
      '@typescript-eslint/no-base-to-string': 'error',
      '@typescript-eslint/restrict-template-expressions': 'error',
      '@typescript-eslint/only-throw-error': 'error',
      // Readability rules — thresholds based on industry standards (Code Complete, SonarQube, BiomeJS)
      'max-lines': ['error', { max: 500, skipBlankLines: true, skipComments: true }],
      'max-lines-per-function': ['error', { max: 200, skipBlankLines: true, skipComments: true, IIFEs: true }],
      complexity: ['error', 20],
      // Aligns with Sonar typescript:S3776 (cognitive complexity). Prefer extraction over suppressions.
      'sonarjs/cognitive-complexity': ['error', 15],
      // Aligns with Sonar typescript:S3358 (nested ternary). Matches SonarCloud carve-outs (e.g. separate JSX `{}` blocks).
      'sonarjs/no-nested-conditional': 'error',
      'max-depth': ['error', 4],
      'max-params': ['error', 5],
      // Limit nested functions/callbacks (e.g. hooks → timeout → setState updater). Complements max-depth
      // and aligns with Sonar-style “deeply nested functions” maintainability rules. Tests disable this.
      'max-nested-callbacks': ['error', 4],
      'import-x/order': [
        'error',
        {
          groups: ['builtin', 'external', 'internal', 'parent', 'sibling', 'index'],
          'newlines-between': 'always',
          alphabetize: { order: 'asc', caseInsensitive: true },
        },
      ],
      'import-x/no-duplicates': 'error',
      'import-x/no-cycle': ['error', { maxDepth: 2 }],
      'import-x/no-self-import': 'error',
      // Do not include file extensions in imports — TypeScript resolves them automatically.
      'import-x/extensions': ['warn', 'never'],
      '@typescript-eslint/consistent-type-definitions': ['error', 'type'],
      // -- syntara custom rules (PR checklist + UX design system enforcement) --
      // no-switch-is-reversed, require-alert-object-param, and require-query-state-object
      // are enforced via no-restricted-syntax AST selectors above (no custom plugin needed).
      'syntara/no-raw-http-calls': [
        'error',
        {
          // XMLHttpRequest required for upload progress (fetch lacks upload progress events)
          allowedFiles: ['**/useFileUploadWithProgress.ts', '**/useFileStorageStatus.ts'],
        },
      ],
      'syntara/prefer-pf-list-components': 'error',
      'syntara/prefer-pf-text-components': 'error',
      'syntara/use-design-tokens-not-hardcoded': 'error',
      'syntara/prefer-confirmation-dialog': 'error',
      'syntara/no-locale-date-format': [
        'error',
        {
          // Canonical Timestamp wrapper components (own dateFormat/timeFormat) + dateUtils.ts
          // (needs raw toLocaleTimeString for the same-day-collapse execution formatters).
          allowedFiles: [
            '**/utils/dateUtils.ts',
            '**/components/table/DateCell.tsx',
            '**/components/table/ExecutionTimestamp.tsx',
            '**/components/table/UserTimestamp.tsx',
            // Composes "Last saved <Timestamp>" inline inside a Tooltip's ReactNode content —
            // no canonical wrapper fits a bare inline timestamp fragment like this.
            '**/routes/builder/SaveWorkflowButton.tsx',
          ],
        },
      ],
      // Catch unnecessary useEffect patterns. Aligns with https://react.dev/learn/you-might-not-need-an-effect
      'reactYouMightNotNeedAnEffect/no-derived-state': 'warn',
      'reactYouMightNotNeedAnEffect/no-chain-state-updates': 'warn',
      'reactYouMightNotNeedAnEffect/no-event-handler': 'warn',
      'reactYouMightNotNeedAnEffect/no-adjust-state-on-prop-change': 'warn',
      'reactYouMightNotNeedAnEffect/no-reset-all-state-on-prop-change': 'warn',
      'reactYouMightNotNeedAnEffect/no-pass-live-state-to-parent': 'warn',
      'reactYouMightNotNeedAnEffect/no-pass-data-to-parent': 'warn',
      'reactYouMightNotNeedAnEffect/no-initialize-state': 'warn',
    },
  },
  {
    // Test utility files that export factory functions alongside components
    files: ['**/test/createTestRouter.tsx'],
    rules: {
      'react-refresh/only-export-components': 'off',
    },
  },
  {
    files: ['**/index.tsx', '**/main.tsx', '**/vite.config.ts', '**/vitest.config.ts', '**/vitest.browser.config.ts'],
    rules: {
      'no-console': 'off',
      'no-restricted-exports': 'off',
      'react-refresh/only-export-components': 'off',
    },
  },
  {
    // Currents requires a default export for its config file — exempt from the default-export ban
    files: ['currents.config.ts'],
    rules: {
      'no-restricted-exports': 'off',
    },
  },
  {
    // Storybook CSF requires `export default meta`; Storybook config files require a default export —
    // exempt both from the default-export ban
    files: ['**/*.stories.{ts,tsx}', '**/.storybook/**/*.{ts,tsx}'],
    rules: {
      'no-restricted-exports': 'off',
      'react-refresh/only-export-components': 'off',
    },
  },
  {
    files: [...TEST_FILES, 'e2e/visual-regression/**/*.ts'],
    rules: {
      'max-lines': 'off',
      'max-lines-per-function': 'off',
      'max-nested-callbacks': 'off',
      complexity: 'off',
      'sonarjs/cognitive-complexity': 'off',
      'syntara/prefer-pf-list-components': 'off',
      'syntara/prefer-pf-text-components': 'off',
      'syntara/use-design-tokens-not-hardcoded': 'off',
      'syntara/prefer-confirmation-dialog': 'off',
      'syntara/no-locale-date-format': 'off',
      'reactYouMightNotNeedAnEffect/no-derived-state': 'off',
      'reactYouMightNotNeedAnEffect/no-chain-state-updates': 'off',
      'reactYouMightNotNeedAnEffect/no-event-handler': 'off',
      'reactYouMightNotNeedAnEffect/no-adjust-state-on-prop-change': 'off',
      'reactYouMightNotNeedAnEffect/no-reset-all-state-on-prop-change': 'off',
      'reactYouMightNotNeedAnEffect/no-pass-live-state-to-parent': 'off',
      'reactYouMightNotNeedAnEffect/no-pass-data-to-parent': 'off',
      'reactYouMightNotNeedAnEffect/no-initialize-state': 'off',
    },
  },
  {
    ...testingLibrary.configs['flat/react'],
    files: TEST_FILES,
    ignores: ['e2e/**'],
    rules: {
      ...testingLibrary.configs['flat/react'].rules,
      'testing-library/no-debugging-utils': 'error',
      // Prefer userEvent over fireEvent for realistic user interaction simulation
      'testing-library/prefer-user-event': 'error',
      'testing-library/no-container': 'warn',
      'testing-library/no-node-access': 'error',
    },
  },
  {
    files: TEST_FILES,
    ignores: ['e2e/**'],
    rules: {
      // Prefer semantic Testing Library queries (getByRole, getByLabelText, etc.) over raw DOM lookups.
      // document.getElementById bypasses a11y semantics and is as fragile as querySelector in tests.
      'no-restricted-properties': [
        'error',
        {
          object: 'document',
          property: 'getElementById',
          message:
            'Use a Testing Library semantic query instead (e.g. screen.getByRole(...)). document.getElementById() bypasses accessibility semantics and is as fragile as container.querySelector().',
        },
        {
          object: 'crypto',
          property: 'randomUUID',
          message:
            'crypto.randomUUID is unavailable over HTTP (non-secure contexts). Use generateUUID() from src/utils/generateUUID.ts or React useId() for component keys.',
        },
      ],
    },
  },
  {
    files: TEST_FILES,
    ignores: ['e2e/**'],
    plugins: { vitest },
    rules: {
      // Aligns with Sonar S2699: every test must contain an explicit assertion call.
      // Custom URL helpers count as assertions when invoked in the test body.
      'vitest/expect-expect': [
        'error',
        {
          // expect* matches local helpers like expectStroke in edge/path tests
          assertFunctionNames: [
            'expect',
            'expect*',
            'assertUrlParam',
            'assertUrlParamIsNull',
            'assertSearchParamsWasCalled',
          ],
        },
      ],
      // Catches duplicate test names in the same describe block -- silently skipped or overwritten.
      'vitest/no-identical-title': 'error',
    },
  },
  {
    files: ['e2e/**/*.spec.ts'],
    rules: {
      // In flat config, array-valued rules replace (not merge with) earlier blocks.
      // This intentionally overrides the general no-restricted-syntax -- E2E files
      // don't use React hooks, formState, or JSX aria-label patterns from above.
      'no-restricted-syntax': [
        'error',
        {
          selector: 'CallExpression[callee.property.name="dispatchEvent"]',
          message:
            'Do not use dispatchEvent() in E2E tests. Use Playwright .click() which simulates real user interaction (scroll, hover, click center). dispatchEvent fires a synthetic event that can mask interaction bugs.',
        },
      ],
      // Targets Playwright locator.first() -- .first() is not a standard JS/Array
      // method, so false positives on non-Playwright code are rare in E2E specs.
      'no-restricted-properties': [
        'error',
        {
          property: 'first',
          message:
            'Avoid .first() — the locator should be specific enough to match exactly one element. If there are duplicates, scope with a parent locator.',
        },
      ],
    },
  },
  {
    // Separate block so the ignores here don't accidentally drop no-restricted-syntax
    // or no-restricted-properties from visual-regression specs (those rules live above).
    // Visual-regression specs intentionally import test from @playwright/test directly
    // to avoid the app fixture so that page.clock can be controlled for determinism.
    files: ['e2e/**/*.spec.ts'],
    ignores: ['e2e/visual-regression/**'],
    rules: {
      'no-restricted-imports': [
        'error',
        {
          patterns: [
            {
              group: ['@playwright/test'],
              importNamePattern: '^test$',
              message:
                "Import `test` from the local fixtures file (e2e/fixtures.ts) instead of @playwright/test directly. The local fixtures extend Playwright's test with Currents action fixtures for automatic flaky test quarantine.",
            },
          ],
        },
      ],
    },
  },
  {
    files: [
      '**/registry/nodes/register*.ts',
      '**/app/App.tsx',
      '**/routes/**/Workflows.tsx',
      '**/routes/**/BuilderNew.tsx',
      '**/routes/**/BuilderEdit.tsx',
      '**/routes/**/Executions.tsx',
      '**/routes/**/ExecutionDetail.tsx',
      '**/routes/**/Integrations.tsx',
      '**/routes/**/IntegrationTools.tsx',
      '**/routes/**/Glossary.tsx',
      '**/routes/**/Settings.tsx',
      '**/routes/**/Approvals.tsx',
      '**/routes/**/Authentication.tsx',
      '**/routes/**/Credentials.tsx',
      '**/routes/**/CredentialDetail.tsx',
      '**/routes/**/CredentialTypes.tsx',
      '**/routes/**/CredentialTypeDetail.tsx',
      '**/vite-env.d.ts',
    ],
    rules: {
      'no-restricted-exports': 'off',
    },
  },
  {
    // Enforce browser tab titles on all top-level page components (default exports) in routes/.
    // Any route file with `export default function Page()` must render
    // <title>{toPageTitle(['...'])}</title>. New pages are covered automatically.
    files: ['**/routes/**/*.tsx'],
    ignores: ['**/*.stories.tsx'],
    rules: {
      'syntara/require-page-title': 'error',
    },
  },
  {
    files: ['e2e/**/*.{ts,tsx}'],
    rules: {
      'react-hooks/rules-of-hooks': 'off',
      'react-refresh/only-export-components': 'off',
      // Testing Library rules target RTL/vitest patterns; Playwright specs use locator-based APIs
      'testing-library/prefer-screen-queries': 'off',
      // Playwright worker-scoped fixtures require destructured first arg even when no deps are needed
      'no-empty-pattern': 'off',
    },
  },
  {
    files: ['**/*.js'],
    ...tseslint.configs.disableTypeChecked,
  },
  ...storybook.configs['flat/recommended'],
  eslintConfigPrettier
)
