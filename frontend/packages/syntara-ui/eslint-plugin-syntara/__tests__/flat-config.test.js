import { ESLint } from 'eslint'
import pluginQuery from '@tanstack/eslint-plugin-query'
import reactUseEffect from 'eslint-plugin-react-you-might-not-need-an-effect'
import tseslint from 'typescript-eslint'
import { describe, expect, it } from 'vitest'
import { mkdtemp, rm, writeFile } from 'node:fs/promises'
import { join, resolve } from 'node:path'

const typeAwareRuleIds = new Set(
  Object.entries(tseslint.plugin.rules)
    .filter(([, rule]) => rule.meta?.docs?.requiresTypeChecking)
    .map(([ruleName]) => `@typescript-eslint/${ruleName}`)
)
// These probes lint synthetic source strings. Project-aware rules try to load them into
// TypeScript projects, which is slow and can fail when the string differs from the file on disk.
// Keep diagnostic probes project-free and check these rules through the resolved config below.
const projectBackedRuleIds = new Set([
  ...typeAwareRuleIds,
  ...Object.keys(pluginQuery.rules).map((ruleName) => `@tanstack/query/${ruleName}`),
  ...Object.keys(reactUseEffect.rules).map((ruleName) => `reactYouMightNotNeedAnEffect/${ruleName}`),
])
const projectBackedRuleOverrides = Object.fromEntries([...projectBackedRuleIds].map((ruleId) => [ruleId, 'off']))
const typeAwareRuleOverrides = Object.fromEntries([...typeAwareRuleIds].map((ruleId) => [ruleId, 'off']))

const eslint = new ESLint({ cwd: process.cwd() })
const eslintProbe = new ESLint({
  cwd: process.cwd(),
  overrideConfig: [
    {
      files: ['**/*.{ts,tsx}'],
      languageOptions: { parserOptions: { project: false } },
      rules: projectBackedRuleOverrides,
    },
  ],
})
const mockApiEslint = new ESLint({
  cwd: resolve(process.cwd(), '../syntara-mock-api'),
  overrideConfig: [
    {
      files: ['**/*.{ts,tsx}'],
      languageOptions: { parserOptions: { project: false } },
      rules: typeAwareRuleOverrides,
    },
  ],
})
const contractsEslint = new ESLint({ cwd: resolve(process.cwd(), '../syntara-contracts') })

const sourceSyntaxProbes = [
  ['Switch isReversed', 'export const auditSwitch = <Switch isReversed />', 'Do not use isReversed'],
  ['positional success alert', "showSuccess('Saved')", 'Pass an object { title, description? }'],
  ['template success alert', 'showSuccess(`Saved`)', 'Pass an object { title, description? }'],
  ['positional error alert', "showError('Failed')", 'Pass an object { title, description? }'],
  ['template error alert', 'showError(`Failed`)', 'Pass an object { title, description? }'],
  ['positional warning alert', "showWarning('Warning')", 'Pass an object { title, description? }'],
  ['template warning alert', 'showWarning(`Warning`)', 'Pass an object { title, description? }'],
  ['positional info alert', "showInfo('Info')", 'Pass an object { title, description? }'],
  ['template info alert', 'showInfo(`Info`)', 'Pass an object { title, description? }'],
  ['string query state', "useQueryState(query, 'Loading')", 'Pass an object { title, onRetry }'],
  ['template query state', 'useQueryState(query, `Loading`)', 'Pass an object { title, onRetry }'],
  ['form submitting state', 'export const auditPending = formState.isSubmitting', 'Do not use formState.isSubmitting'],
  ['span aria-label', 'export const auditSpan = <span aria-label="status" />', 'Do not use aria-label on <span>'],
  [
    'FormSelect import',
    "import { FormSelect } from '@patternfly/react-core'",
    'Use SynSelect with PatternFly SelectList',
  ],
  [
    'FormSelectOption import',
    "import { FormSelectOption } from '@patternfly/react-core'",
    'Use SynSelect with PatternFly SelectList',
  ],
  [
    'deprecated routing bridge import',
    "import { useNavigate } from '../hooks/routing/useNavigate'",
    'Deprecated bridge hook',
  ],
  ['native select', 'export const auditSelect = <select />', 'Do not use native <select>'],
]

const directRuleProbes = [
  ['eqeqeq', 'export const result = 1 == 1', 'eqeqeq'],
  ['no-void', 'export const result = void 0', 'no-void'],
  ['no-console', "console.log('probe')", 'no-console'],
  ['no-floating-promises', 'Promise.resolve(1)', '@typescript-eslint/no-floating-promises'],
  ['no-misused-promises', 'if (Promise.resolve(true)) { console.log(1) }', '@typescript-eslint/no-misused-promises'],
  ['no-explicit-any', 'export const value: any = 1', '@typescript-eslint/no-explicit-any'],
  [
    'no-unsafe-argument',
    'declare const unsafe: any; declare function accept(value: string): void; accept(unsafe)',
    '@typescript-eslint/no-unsafe-argument',
  ],
  [
    'no-unsafe-assignment',
    'declare const unsafe: any; export const value: string = unsafe',
    '@typescript-eslint/no-unsafe-assignment',
  ],
  ['no-unsafe-call', 'declare const unsafe: any; export const value = unsafe()', '@typescript-eslint/no-unsafe-call'],
  [
    'no-unsafe-member-access',
    'declare const unsafe: any; export const value = unsafe.foo',
    '@typescript-eslint/no-unsafe-member-access',
  ],
  [
    'no-unsafe-return',
    'declare const unsafe: any; export function f(): string { return unsafe }',
    '@typescript-eslint/no-unsafe-return',
  ],
  ['await-thenable', 'export async function f() { return await 1 }', '@typescript-eslint/await-thenable'],
  ['require-await', 'export async function f() { return 1 }', '@typescript-eslint/require-await'],
  [
    'unbound-method',
    'class Probe { method() { return this } }; const probe = new Probe(); export const method = probe.method',
    '@typescript-eslint/unbound-method',
  ],
  ['no-base-to-string', 'export const text = `${{}}`', '@typescript-eslint/no-base-to-string'],
  [
    'restrict-template-expressions',
    'declare const value: object; export const text = `${value}`',
    '@typescript-eslint/restrict-template-expressions',
  ],
  [
    'no-unused-private-class-members',
    'export class Probe { #unused() {} }',
    '@typescript-eslint/no-unused-private-class-members',
  ],
  [
    'no-unnecessary-type-assertion',
    "const value: string = 'x'; export const result = value as string",
    '@typescript-eslint/no-unnecessary-type-assertion',
  ],
  [
    'no-non-null-assertion',
    'const value: string | undefined = undefined; export const result = value!',
    '@typescript-eslint/no-non-null-assertion',
  ],
  ['no-restricted-exports', 'export default function Probe() { return <title>Probe</title> }', 'no-restricted-exports'],
  [
    'react/no-array-index-key',
    'export const Probe = ({ items }: { items: string[] }) => <ul>{items.map((item, index) => <li key={index}>{item}</li>)}</ul>',
    'react/no-array-index-key',
  ],
  [
    'react/jsx-no-constructed-context-values',
    'const C = createContext({}); export const Probe = () => <C.Provider value={{ x: 1 }} />',
    'react/jsx-no-constructed-context-values',
  ],
  ['react/jsx-no-useless-fragment', 'export const Probe = () => <><div /></>', 'react/jsx-no-useless-fragment'],
  ['react/self-closing-comp', 'export const Probe = () => <div></div>', 'react/self-closing-comp'],
  ['unicorn/prefer-number-properties', "export const value = parseInt('1', 10)", 'unicorn/prefer-number-properties'],
  [
    'unicorn/consistent-template-literal-escape',
    'export const value = `hello $\\{world}`',
    'unicorn/consistent-template-literal-escape',
  ],
  [
    'unicorn/no-useless-iterator-to-array',
    'export const value = new Set([1, 2].values().toArray())',
    'unicorn/no-useless-iterator-to-array',
  ],
  [
    'unicorn/prefer-simple-condition-first',
    'export function f(flag: boolean, check: boolean, other: boolean, ready: boolean) { if ((flag ? check : other) && ready) return 1; return 0 }',
    'unicorn/prefer-simple-condition-first',
  ],
  [
    'unicorn/switch-case-break-position',
    'switch (value) { case 1: { run() } break }',
    'unicorn/switch-case-break-position',
  ],
  [
    '@typescript-eslint/prefer-optional-chain',
    'type T = { a?: { b: string } }; export const f = (x: T | undefined) => x && x.a && x.a.b',
    '@typescript-eslint/prefer-optional-chain',
  ],
  [
    '@typescript-eslint/prefer-nullish-coalescing',
    'export const f = (x: number | undefined) => x || 4',
    '@typescript-eslint/prefer-nullish-coalescing',
  ],
  [
    '@typescript-eslint/require-array-sort-compare',
    'export const value = [2, 10].sort()',
    '@typescript-eslint/require-array-sort-compare',
  ],
  [
    '@typescript-eslint/switch-exhaustiveness-check',
    "type T = 'a' | 'b'; export function f(x: T) { switch (x) { case 'a': return 1 } }",
    '@typescript-eslint/switch-exhaustiveness-check',
  ],
  [
    '@typescript-eslint/prefer-includes',
    "export const f = (x: string) => ['a', 'b'].indexOf(x) !== -1",
    '@typescript-eslint/prefer-includes',
  ],
  ['@typescript-eslint/only-throw-error', "export function f() { throw 'bad' }", '@typescript-eslint/only-throw-error'],
  ['max-params', 'export function f(a, b, c, d, e) { return a }', 'max-params'],
  [
    'max-nested-callbacks',
    'export function audit() { fn(() => fn(() => fn(() => fn(() => fn(() => 1))))) }',
    'max-nested-callbacks',
  ],
  [
    'max-depth',
    'export function f(a) { if(a) { if(a) { if(a) { if(a) { if(a) return 1 } } } } return 0 }',
    'max-depth',
  ],
  ['sonarjs/no-nested-conditional', 'export const f = (a, b, c) => a ? b ? 1 : 2 : 3', 'sonarjs/no-nested-conditional'],
  [
    'import-x/no-duplicates',
    "import { x } from 'react'; import { y } from 'react'; export { x, y }",
    'import-x/no-duplicates',
  ],
  ['import-x/no-self-import', "import './AssignRoleModal.tsx'", 'import-x/no-self-import'],
  [
    'import-x/extensions',
    "import { WorkflowStore } from '../../stores/workflowStoreTypes.ts'; export type AuditWorkflowStore = WorkflowStore",
    'import-x/extensions',
  ],
  [
    '@typescript-eslint/consistent-type-definitions',
    'export interface Probe { value: string }',
    '@typescript-eslint/consistent-type-definitions',
  ],
]

const reactHooksAndA11yProbes = [
  [
    'rules of hooks',
    'export function Probe({ enabled }: { enabled: boolean }) { if (enabled) { const [value] = useState(0); return value } return null }',
    'react-hooks/rules-of-hooks',
  ],
  [
    'exhaustive effect dependencies',
    "import { useEffect } from 'react'; export function Probe({ value }: { value: string }) { useEffect(() => { console.log(value) }, []); return null }",
    'react-hooks/exhaustive-deps',
  ],
  [
    'ref read during render',
    "import { useRef } from 'react'; export function Probe() { const ref = useRef(0); return <span>{ref.current}</span> }",
    'react-hooks/refs',
  ],
  [
    'state update in effect',
    "import { useEffect, useState } from 'react'; export function Probe() { const [value, setValue] = useState(0); useEffect(() => { setValue(1) }, []); return <span>{value}</span> }",
    'react-hooks/set-state-in-effect',
  ],
  [
    'non-interactive tab stop',
    'export const Probe = () => <div tabIndex={0} />',
    'jsx-a11y/no-noninteractive-tabindex',
  ],
  [
    'React Refresh mixed exports',
    'export const Probe = () => null; export const helper = () => 1',
    'react-refresh/only-export-components',
  ],
  [
    'import ordering',
    "import { useState } from 'react'; import fs from 'node:fs'; export { fs, useState }",
    'import-x/order',
  ],
  [
    'source non-null assertion',
    'const value: string | undefined = undefined; export const result = value!',
    '@typescript-eslint/no-non-null-assertion',
  ],
]

const reactEffectWarningProbes = [
  [
    'derived state',
    "import { useEffect, useState } from 'react'; export function Probe({ first, last }: { first: string; last: string }) { const [fullName, setFullName] = useState(''); useEffect(() => { setFullName(first + last) }, [first, last]); return <span>{fullName}</span> }",
    'reactYouMightNotNeedAnEffect/no-derived-state',
  ],
  [
    'chained state update',
    "import { useEffect, useState } from 'react'; export function Probe() { const [round] = useState(1); const [isOver, setIsOver] = useState(false); useEffect(() => { if (round > 10) setIsOver(true) }, [round]); return <span>{String(isOver)}</span> }",
    'reactYouMightNotNeedAnEffect/no-chain-state-updates',
  ],
  [
    'effect used as event handler',
    "import { useEffect } from 'react'; export function Probe({ product, show }: { product: { isInCart: boolean; name: string }; show: (text: string) => void }) { useEffect(() => { if (product.isInCart) show(`Added ${product.name}`) }, [product, show]); return null }",
    'reactYouMightNotNeedAnEffect/no-event-handler',
  ],
  [
    'state adjusted when prop changes',
    "import { useEffect, useState } from 'react'; export function Probe({ items }: { items: string[] }) { const [selection, setSelection] = useState<string | null>(null); useEffect(() => { setSelection(null) }, [items]); return <div>{selection}</div> }",
    'reactYouMightNotNeedAnEffect/no-adjust-state-on-prop-change',
  ],
  [
    'all state reset when prop changes',
    "import { useEffect, useState } from 'react'; export function Probe({ items }: { items: string[] }) { const [selection, setSelection] = useState<string | null>(null); useEffect(() => { setSelection(null) }, [items]); return null }",
    'reactYouMightNotNeedAnEffect/no-reset-all-state-on-prop-change',
  ],
  [
    'live state passed to parent',
    "import { useEffect, useState } from 'react'; export function Probe({ onChange }: { onChange: (value: number) => void }) { const [value] = useState(0); useEffect(() => { onChange(value) }, [onChange, value]); return null }",
    'reactYouMightNotNeedAnEffect/no-pass-live-state-to-parent',
  ],
  [
    'query data passed to parent',
    "import { useEffect } from 'react'; import { useQuery } from '@tanstack/react-query'; export function Probe({ onDataFetched }: { onDataFetched: (data: number) => void }) { const { data } = useQuery({ queryKey: ['probe'], queryFn: async () => 1 }); useEffect(() => { onDataFetched(data) }, [data, onDataFetched]); return null }",
    'reactYouMightNotNeedAnEffect/no-pass-data-to-parent',
  ],
  [
    'state initialized in effect',
    "import { useEffect, useState } from 'react'; export function Probe() { const [value, setValue] = useState(0); useEffect(() => { setValue(1) }, []); return <span>{value}</span> }",
    'reactYouMightNotNeedAnEffect/no-initialize-state',
  ],
]

const testProfileRuleProbes = [
  ['focused test', "describe.only('focused', () => {})", 'no-only-tests/no-only-tests'],
  [
    'Testing Library node access',
    "import { render } from '@testing-library/react'; const view = render(<div />); view.container.querySelector('div')",
    'testing-library/no-node-access',
  ],
  [
    'Testing Library user event',
    "import { fireEvent, screen } from '@testing-library/react'; fireEvent.click(screen.getByRole('button'))",
    'testing-library/prefer-user-event',
  ],
  [
    'Testing Library debugging utility',
    "import { screen } from '@testing-library/react'; screen.debug()",
    'testing-library/no-debugging-utils',
  ],
  [
    'Testing Library render queries',
    "import { render } from '@testing-library/react'; const view = render(<button />); view.getByRole('button')",
    'testing-library/prefer-screen-queries',
  ],
  [
    'Testing Library container access',
    "import { render } from '@testing-library/react'; const { container } = render(<div />); container.querySelector('div')",
    'testing-library/no-container',
  ],
  [
    'Vitest test without assertion',
    "import { it } from 'vitest'; it('does something', () => {})",
    'vitest/expect-expect',
  ],
  [
    'duplicate Vitest title',
    "import { describe, it } from 'vitest'; describe('group', () => { it('same', () => {}); it('same', () => {}) })",
    'vitest/no-identical-title',
  ],
]

const tanstackQueryProbes = [
  [
    'query key dependencies',
    "import { useQuery } from '@tanstack/react-query'; export function Probe({ id }: { id: string }) { return useQuery({ queryKey: ['item'], queryFn: () => fetchItem(id) }) }",
    '@tanstack/query/exhaustive-deps',
  ],
  [
    'query result rest destructuring',
    "import { useQuery } from '@tanstack/react-query'; export function Probe() { const { data, ...rest } = useQuery({ queryKey: ['item'], queryFn: async () => 1 }); return <div>{String(data)}{String(rest)}</div> }",
    '@tanstack/query/no-rest-destructuring',
  ],
  [
    'unstable QueryClient',
    "import { QueryClient } from '@tanstack/react-query'; export function Probe() { const client = new QueryClient(); return client }",
    '@tanstack/query/stable-query-client',
  ],
  [
    'query result in hook dependencies',
    "import { useEffect } from 'react'; import { useQuery } from '@tanstack/react-query'; export function Probe() { const query = useQuery({ queryKey: ['item'], queryFn: async () => 1 }); useEffect(() => { console.log(query.data) }, [query]); return null }",
    '@tanstack/query/no-unstable-deps',
  ],
  [
    'infinite query option order',
    "import { useInfiniteQuery } from '@tanstack/react-query'; export function Probe() { return useInfiniteQuery({ getNextPageParam: () => undefined, queryFn: async () => 1, queryKey: ['item'], initialPageParam: 0 }) }",
    '@tanstack/query/infinite-query-property-order',
  ],
  [
    'query function return value',
    "import { useQuery } from '@tanstack/react-query'; export function Probe() { return useQuery({ queryKey: ['item'], queryFn: () => undefined }) }",
    '@tanstack/query/no-void-query-fn',
  ],
  [
    'mutation option order',
    "import { useMutation } from '@tanstack/react-query'; export function Probe() { return useMutation({ onError: () => {}, onMutate: () => ({}) }) }",
    '@tanstack/query/mutation-property-order',
  ],
]

const e2eSyntaxProbes = [
  ['networkidle wait', "await page.waitForLoadState('networkidle')", "Do not use waitForLoadState('networkidle')"],
  ['dispatchEvent', "await page.dispatchEvent('button', 'click')", 'Do not use dispatchEvent() in E2E tests'],
  [
    'PatternFly locator selector',
    "await page.locator('.pf-v6-button').click()",
    'Do not use PatternFly CSS class selectors in locator()',
  ],
  [
    'workflow URL shortcut',
    'await expect(page).toHaveURL(/workflow-builder\\/.+/)',
    'Do not gate a workflow save on toHaveURL',
  ],
]

const e2ePropertyProbes = [
  ['first', "await page.locator('button').first().click()", 'Avoid .first()'],
  ['nth', "await page.locator('button').nth(0).click()", 'Avoid .nth()'],
]

const mathRandomProbePaths = [
  'src/routes/access-management/AssignRoleModal.tsx',
  'src/routes/access-management/groupFieldHelp.test.tsx',
  'e2e/credentials-misc.spec.ts',
  'e2e/helpers/workflow-payload.ts',
  'e2e/fixtures.ts',
  'e2e/visual-regression/page-screenshots.spec.ts',
]

async function lintMessages(filePath, code) {
  const [result] = await eslintProbe.lintText(code, { filePath })
  return result.messages
}

describe('flat ESLint config rule inheritance', () => {
  it.each(directRuleProbes)(
    'activates the configured rule: %s',
    async (_name, code, expectedRuleId) => {
      if (projectBackedRuleIds.has(expectedRuleId)) {
        const config = await eslint.calculateConfigForFile('src/routes/access-management/AssignRoleModal.tsx')

        expect(config?.rules[expectedRuleId]?.[0] ?? 0).toBeGreaterThan(0)
        return
      }

      const messages = await lintMessages('src/routes/access-management/AssignRoleModal.tsx', code)

      expect(messages.some((message) => message.ruleId === expectedRuleId)).toBe(true)
    },
    30_000
  )

  it.each(reactHooksAndA11yProbes)(
    'enforces the React and accessibility rule: %s',
    async (_name, code, expectedRuleId) => {
      const messages = await lintMessages('src/routes/access-management/AssignRoleModal.tsx', code)

      expect(messages.some((message) => message.ruleId === expectedRuleId && message.severity === 2)).toBe(true)
    },
    30_000
  )

  it('allows keyboard focus on a named region', async () => {
    const messages = await lintMessages(
      'src/routes/access-management/AssignRoleModal.tsx',
      'export const Probe = () => <div role="region" tabIndex={0} aria-label="Results" />'
    )

    expect(messages.some((message) => message.ruleId === 'jsx-a11y/no-noninteractive-tabindex')).toBe(false)
  })

  it.each(reactEffectWarningProbes)(
    'surfaces the configured React effect warning: %s',
    async (_name, _code, expectedRuleId) => {
      const config = await eslint.calculateConfigForFile('src/routes/access-management/AssignRoleModal.tsx')

      expect(config?.rules[expectedRuleId]?.[0]).toBe(1)
    },
    30_000
  )

  it.each(testProfileRuleProbes)(
    'enforces the test-only rule: %s',
    async (_name, code, expectedRuleId) => {
      const messages = await lintMessages('src/routes/access-management/groupFieldHelp.test.tsx', code)

      expect(messages.some((message) => message.ruleId === expectedRuleId)).toBe(true)
    },
    30_000
  )

  it.each(tanstackQueryProbes)(
    'enforces the TanStack Query rule: %s',
    async (_name, _code, expectedRuleId) => {
      const config = await eslint.calculateConfigForFile('src/routes/access-management/AssignRoleModal.tsx')

      expect(config?.rules[expectedRuleId]?.[0] ?? 0).toBeGreaterThan(0)
    },
    30_000
  )

  it('detects circular TypeScript imports', async () => {
    const probeDirectory = await mkdtemp(join(process.cwd(), 'src/eslint-cycle-probe-'))
    const firstFile = join(probeDirectory, 'first.ts')
    const secondFile = join(probeDirectory, 'second.ts')

    try {
      await writeFile(firstFile, "import { second } from './second'; export const first: number = second")
      await writeFile(secondFile, "import { first } from './first'; export const second: number = first")

      const results = await eslintProbe.lintFiles([firstFile, secondFile])
      const messages = results.flatMap((result) => result.messages)

      expect(messages.some((message) => message.ruleId === 'import-x/no-cycle')).toBe(true)
    } finally {
      await rm(probeDirectory, { recursive: true, force: true })
    }
  })

  it('keeps TypeScript cycle detection enabled outside the intentional store-selector facade', async () => {
    const sourceConfig = await eslint.calculateConfigForFile('src/routes/access-management/AssignRoleModal.tsx')
    const storeConfig = await eslint.calculateConfigForFile('src/stores/useWorkflowStore.ts')

    expect(sourceConfig?.rules['import-x/no-cycle']?.[0]).toBe(2)
    expect(storeConfig?.rules['import-x/no-cycle']?.[0]).toBe(0)
    expect(sourceConfig?.settings['import-x/extensions']).toContain('.ts')
    expect(sourceConfig?.settings['import-x/resolver-next']).toHaveLength(1)
  })

  it('keeps warning-level source rules active', async () => {
    const commentMessages = await lintMessages(
      'src/routes/access-management/AssignRoleModal.tsx',
      '// TODO: verify this probe\nexport const value = 1'
    )
    const barrelMessages = await lintMessages(
      'src/constants/index.ts',
      "export { a } from './a'; export { b } from './b'; export { c } from './c'; export { d } from './d'"
    )

    expect(commentMessages.some((message) => message.ruleId === 'no-warning-comments' && message.severity === 1)).toBe(
      true
    )
    expect(
      barrelMessages.some((message) => message.ruleId === 'barrel-files/avoid-barrel-files' && message.severity === 1)
    ).toBe(true)
  })

  it('allows required JSON extensions while warning on TypeScript extensions', async () => {
    const jsonMessages = await lintMessages(
      'src/routes/access-management/AssignRoleModal.tsx',
      "import docs from '../../utils/docs/docsUrls.json'; export { docs }"
    )

    expect(jsonMessages.some((message) => message.ruleId === 'import-x/extensions')).toBe(false)
  })

  it('loads every Syntara custom rule in the route source profile', async () => {
    const config = await eslint.calculateConfigForFile('src/routes/access-management/AssignRoleModal.tsx')
    const customRuleIds = [
      'syntara/no-hardcoded-doc-urls',
      'syntara/no-locale-date-format',
      'syntara/no-nested-component-definitions',
      'syntara/no-raw-http-calls',
      'syntara/prefer-confirmation-dialog',
      'syntara/prefer-syn-select',
      'syntara/prefer-pf-list-components',
      'syntara/prefer-pf-text-components',
      'syntara/require-page-title',
      'syntara/use-design-tokens-not-hardcoded',
    ]

    expect(customRuleIds.every((ruleId) => config?.rules[ruleId]?.[0] === 2)).toBe(true)
  })

  it('enforces the configured complexity and file-size thresholds', async () => {
    const longFile = Array.from({ length: 501 }, (_, index) => `export const auditLine${index} = ${index}`).join('\n')
    const longFunction = `export function auditFunction() {\n${Array.from({ length: 201 }, (_, index) => `  const auditValue${index} = ${index}`).join('\n')}\n  return auditValue200\n}`
    const branchingFunction = `export function auditComplexity(value: number) {\n${Array.from({ length: 21 }, (_, index) => `  if (value === ${index}) return ${index}`).join('\n')}\n  return -1\n}`
    const lineMessages = await lintMessages('src/routes/access-management/AssignRoleModal.tsx', longFile)
    const functionMessages = await lintMessages('src/routes/access-management/AssignRoleModal.tsx', longFunction)
    const complexityMessages = await lintMessages('src/routes/access-management/AssignRoleModal.tsx', branchingFunction)

    expect(lineMessages.some((message) => message.ruleId === 'max-lines')).toBe(true)
    expect(functionMessages.some((message) => message.ruleId === 'max-lines-per-function')).toBe(true)
    expect(complexityMessages.some((message) => message.ruleId === 'complexity')).toBe(true)
    expect(complexityMessages.some((message) => message.ruleId === 'sonarjs/cognitive-complexity')).toBe(true)
  }, 30_000)

  it.each(sourceSyntaxProbes)(
    'enforces the shared source restriction: %s',
    async (_name, code, messageFragment) => {
      const messages = await lintMessages('src/routes/access-management/AssignRoleModal.tsx', code)

      expect(
        messages.some(
          (message) => message.ruleId === 'no-restricted-syntax' && message.message.includes(messageFragment)
        )
      ).toBe(true)
    },
    30_000
  )

  it.each(mathRandomProbePaths)(
    'keeps the Math.random restriction for %s',
    async (filePath) => {
      const messages = await lintMessages(filePath, 'export const auditId = Math.random()')

      expect(
        messages.some((message) => message.ruleId === 'no-restricted-syntax' && message.message.includes('Math.random'))
      ).toBe(true)
    },
    30_000
  )

  it('keeps the crypto.randomUUID restriction in E2E specs', async () => {
    const messages = await lintMessages('e2e/credentials-misc.spec.ts', 'export const auditId = crypto.randomUUID()')

    expect(
      messages.some(
        (message) => message.ruleId === 'no-restricted-properties' && message.message.includes('crypto.randomUUID')
      )
    ).toBe(true)
  }, 30_000)

  it.each(e2ePropertyProbes)(
    'enforces the E2E property restriction: %s',
    async (_name, code, messageFragment) => {
      const messages = await lintMessages(
        'e2e/credentials-misc.spec.ts',
        `async function audit(page: Page) { ${code} }`
      )

      expect(
        messages.some(
          (message) => message.ruleId === 'no-restricted-properties' && message.message.includes(messageFragment)
        )
      ).toBe(true)
    },
    30_000
  )

  it.each(e2eSyntaxProbes)('enforces the E2E spec restriction: %s', async (_name, code, messageFragment) => {
    const messages = await lintMessages('e2e/credentials-misc.spec.ts', `async function audit(page: Page) { ${code} }`)

    expect(
      messages.some((message) => message.ruleId === 'no-restricted-syntax' && message.message.includes(messageFragment))
    ).toBe(true)
  })

  it('requires a page title when a route uses a locally aliased default export', async () => {
    const messages = await lintMessages(
      'src/routes/access-management/AssignRoleModal.tsx',
      'function AuditPage() { return <h1>Audit</h1> } export { AuditPage as default }'
    )

    expect(messages.some((message) => message.ruleId === 'syntara/require-page-title')).toBe(true)
    expect(messages.some((message) => message.ruleId === 'no-restricted-exports')).toBe(false)
  })

  it('keeps unit-test rules scoped to test files', async () => {
    const sourceConfig = await eslint.calculateConfigForFile('src/routes/access-management/AssignRoleModal.tsx')
    const testConfig = await eslint.calculateConfigForFile('src/routes/access-management/groupFieldHelp.test.tsx')

    expect(sourceConfig?.rules['vitest/expect-expect']?.[0] ?? 0).toBe(0)
    expect(testConfig?.rules['vitest/expect-expect']?.[0]).toBe(2)
    expect(sourceConfig?.rules['syntara/no-hardcoded-doc-urls']?.[0]).toBe(2)
    expect(testConfig?.rules['syntara/no-hardcoded-doc-urls']?.[0]).toBe(0)
    expect(sourceConfig?.rules['@typescript-eslint/no-non-null-assertion']?.[0]).toBe(2)
    expect(testConfig?.rules['@typescript-eslint/no-non-null-assertion']?.[0]).toBe(0)
  })

  it('keeps E2E imports restricted while allowing the project fixtures path', async () => {
    const messages = await lintMessages(
      'e2e/credentials-misc.spec.ts',
      "import { test } from '@playwright/test'; import type { Page } from '@playwright/test'; export type AuditPage = Page"
    )

    expect(messages.filter((message) => message.ruleId === 'no-restricted-imports')).toHaveLength(2)
  })

  it('applies import restrictions only in the intended source profiles', async () => {
    const iconSourceMessages = await lintMessages(
      'src/routes/access-management/AssignRoleModal.tsx',
      "import { SearchIcon } from '@patternfly/react-icons'; export { SearchIcon }"
    )
    const iconTestMessages = await lintMessages(
      'src/routes/access-management/groupFieldHelp.test.tsx',
      "import { SearchIcon } from '@patternfly/react-icons'; export { SearchIcon }"
    )
    const bridgeImportMessages = await lintMessages(
      'src/routes/access-management/AssignRoleModal.tsx',
      "import { useNavigate } from '../hooks/routing/useNavigate'; export { useNavigate }"
    )
    const routerLinkMessages = await lintMessages(
      'src/routes/access-management/AssignRoleModal.tsx',
      "import { Link } from '@tanstack/react-router'; export { Link }"
    )
    const internalContractMessages = await lintMessages(
      'src/routes/access-management/AssignRoleModal.tsx',
      "import { Workflow } from '@syntara/contracts/src/workflow-api'; export { Workflow }"
    )
    const routingBridgeMessages = await lintMessages(
      'src/hooks/routing/Link.tsx',
      "import { Link as TanStackLink } from '@tanstack/react-router'; export { TanStackLink }"
    )
    const synLinkMessages = await lintMessages(
      'src/components/SynLink.tsx',
      "import { Link } from '@tanstack/react-router'; export { Link }"
    )

    expect(
      iconSourceMessages.some((message) => message.ruleId === 'no-restricted-imports' && message.severity === 1)
    ).toBe(true)
    expect(iconTestMessages.some((message) => message.ruleId === 'no-restricted-imports')).toBe(false)
    expect(bridgeImportMessages.some((message) => message.ruleId === '@typescript-eslint/no-restricted-imports')).toBe(
      true
    )
    expect(routerLinkMessages.some((message) => message.ruleId === '@typescript-eslint/no-restricted-imports')).toBe(
      true
    )
    expect(
      internalContractMessages.some((message) => message.ruleId === '@typescript-eslint/no-restricted-imports')
    ).toBe(true)
    expect(routingBridgeMessages.some((message) => message.ruleId === '@typescript-eslint/no-restricted-imports')).toBe(
      false
    )
    expect(synLinkMessages.some((message) => message.ruleId === '@typescript-eslint/no-restricted-imports')).toBe(false)
  })

  it('keeps Storybook export/import exceptions in the story profile', async () => {
    const messages = await lintMessages(
      'src/components/panels/list/SynListPanel.stories.tsx',
      "import { Meta } from '@storybook/react-vite'; export default Meta"
    )

    expect(
      messages.some(
        (message) => message.ruleId === '@typescript-eslint/no-restricted-imports' && message.severity === 2
      )
    ).toBe(true)
    expect(messages.some((message) => message.ruleId === 'no-restricted-exports')).toBe(false)
    expect(messages.some((message) => message.ruleId === 'storybook/default-exports')).toBe(false)
  })

  it('allows direct default exports only in configured app entry points', async () => {
    const routeMessages = await lintMessages(
      'src/routes/access-management/AssignRoleModal.tsx',
      'export default function AuditPage() { return <title>Audit</title> }'
    )
    const allowlistedRouteMessages = await lintMessages(
      'src/routes/approvals/Approvals.tsx',
      'export default function AuditPage() { return <title>Audit</title> }'
    )

    expect(routeMessages.some((message) => message.ruleId === 'no-restricted-exports')).toBe(true)
    expect(allowlistedRouteMessages.some((message) => message.ruleId === 'no-restricted-exports')).toBe(false)
  })

  it('keeps the test-only DOM lookup restriction', async () => {
    const messages = await lintMessages(
      'src/routes/access-management/groupFieldHelp.test.tsx',
      'export const auditLookup = document.getElementById("target")'
    )

    expect(
      messages.some(
        (message) => message.ruleId === 'no-restricted-properties' && message.message.includes('getElementById')
      )
    ).toBe(true)
  }, 30_000)

  it('scopes deterministic mock dates and generated-contract ignores to their packages', async () => {
    const seedMessages = await mockApiEslint.lintText('export const auditDate = new Date()', {
      filePath: 'src/resources/users.ts',
    })
    const nonSeedMessages = await mockApiEslint.lintText('export const auditDate = new Date()', {
      filePath: 'src/index.ts',
    })

    expect(seedMessages[0]?.messages.some((message) => message.ruleId === 'no-restricted-syntax')).toBe(true)
    expect(nonSeedMessages[0]?.messages.some((message) => message.ruleId === 'no-restricted-syntax')).toBe(false)
    expect(await contractsEslint.isPathIgnored('src/workflow-api.ts')).toBe(true)
    expect(await contractsEslint.isPathIgnored('src/interfaces.ts')).toBe(false)
  })
})
