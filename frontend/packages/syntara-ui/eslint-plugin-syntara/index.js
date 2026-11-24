import noLocaleDateFormat from './rules/no-locale-date-format.js'
import preferConfirmationDialog from './rules/prefer-confirmation-dialog.js'
import preferSynSelect from './rules/prefer-syn-select.js'
import preferPfListComponents from './rules/prefer-pf-list-components.js'
import preferPfTextComponents from './rules/prefer-pf-text-components.js'
import requirePageTitle from './rules/require-page-title.js'
import useDesignTokensNotHardcoded from './rules/use-design-tokens-not-hardcoded.js'

/** @type {import('eslint').ESLint.Plugin} */
export default {
  meta: { name: 'eslint-plugin-syntara', version: '0.1.0' },
  rules: {
    'no-locale-date-format': noLocaleDateFormat,
    'prefer-confirmation-dialog': preferConfirmationDialog,
    'prefer-syn-select': preferSynSelect,
    'prefer-pf-list-components': preferPfListComponents,
    'prefer-pf-text-components': preferPfTextComponents,
    'require-page-title': requirePageTitle,
    'use-design-tokens-not-hardcoded': useDesignTokensNotHardcoded,
  },
}
