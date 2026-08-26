import noHardcodedDocUrls from './rules/no-hardcoded-doc-urls.js'
import noLocaleDateFormat from './rules/no-locale-date-format.js'
import noNestedComponentDefinitions from './rules/no-nested-component-definitions.js'
import noRawHttpCalls from './rules/no-raw-http-calls.js'
import preferConfirmationDialog from './rules/prefer-confirmation-dialog.js'
import preferPfListComponents from './rules/prefer-pf-list-components.js'
import preferPfTextComponents from './rules/prefer-pf-text-components.js'
import requirePageTitle from './rules/require-page-title.js'
import useDesignTokensNotHardcoded from './rules/use-design-tokens-not-hardcoded.js'

/** @type {import('eslint').ESLint.Plugin} */
export default {
  meta: { name: 'eslint-plugin-syntara', version: '0.1.0' },
  rules: {
    'no-hardcoded-doc-urls': noHardcodedDocUrls,
    'no-locale-date-format': noLocaleDateFormat,
    'no-nested-component-definitions': noNestedComponentDefinitions,
    'no-raw-http-calls': noRawHttpCalls,
    'prefer-confirmation-dialog': preferConfirmationDialog,
    'prefer-pf-list-components': preferPfListComponents,
    'prefer-pf-text-components': preferPfTextComponents,
    'require-page-title': requirePageTitle,
    'use-design-tokens-not-hardcoded': useDesignTokensNotHardcoded,
  },
}
