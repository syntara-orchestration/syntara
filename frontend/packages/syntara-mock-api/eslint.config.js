import js from '@eslint/js'
import tseslint from 'typescript-eslint'

export default tseslint.config(
  { ignores: ['dist'] },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    languageOptions: { parserOptions: { tsconfigRootDir: import.meta.dirname } },
  },
  {
    files: ['src/resources/**/*.ts', 'src/utils/**/*.ts'],
    rules: {
      'no-restricted-syntax': [
        'error',
        {
          selector: 'NewExpression[callee.name="Date"][arguments.length=0]',
          message:
            'Do not use `new Date()` in seed data — it produces non-deterministic timestamps that break visual regression baselines. Import from `mockDates.ts` instead.',
        },
      ],
    },
  }
)
