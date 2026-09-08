/**
 * Enforce frontend/AGENTS.md checklist item #27: Use `useDocLink` for
 * documentation URLs — never hardcode doc URLs.
 *
 * Detects string/template literals that match the allowlisted registry prefixes
 * unless the file is the canonical definition site (docsUrls.json, useDocLink.ts)
 * or a test file.
 */

/** Prefixes resolved via useDocLink / docsUrls.json — must not be inlined elsewhere. */
const DOC_URL_PREFIXES = [
  'https://access.redhat.com/documentation/',
  'https://docs.redhat.com/',
  'https://docs.ansible.com/',
  'https://ansible.readthedocs.io/',
]

/**
 * Return true when the string value starts with one of the guarded URL prefixes.
 *
 * @param {string} value
 * @returns {boolean}
 */
function isDocUrl(value) {
  return DOC_URL_PREFIXES.some((prefix) => value.startsWith(prefix))
}

/**
 * Return true when the file should be skipped entirely:
 * - docsUrls.json  — the canonical URL registry
 * - useDocLink.ts  — the hook implementation that reads the registry
 * - *.test.ts / *.test.tsx / *.spec.ts / *.spec.tsx — test files may hardcode
 *   URLs for assertion purposes
 *
 * @param {string} filename
 * @returns {boolean}
 */
function isExemptFile(filename) {
  const normalized = filename.replace(/\\/g, '/')
  return (
    normalized.endsWith('/docsUrls.json') ||
    normalized.endsWith('/useDocLink.ts') ||
    /\.(test|spec)\.[jt]sx?$/.test(normalized)
  )
}

/** @type {import('eslint').Rule.RuleModule} */
export default {
  meta: {
    type: 'problem',
    docs: {
      description:
        "Disallow hardcoded documentation URLs. Use `useDocLink('key')` from `src/utils/docs/useDocLink.ts` and pass the result to `SynPageHeader`'s `docLink` prop. Add new keys to `docsUrls.json` when adding new pages.",
      recommended: true,
      url: 'See frontend/AGENTS.md checklist item #27 and `.claude/skills/frontend-coding-standards/SKILL.md` section 33.',
    },
    messages: {
      noHardcodedDocUrl:
        "Hardcoded documentation URL detected. Use `useDocLink('key')` from `src/utils/docs/useDocLink.ts` and add the key to `docsUrls.json` if needed.",
    },
    schema: [],
  },

  create(context) {
    const filename = context.physicalFilename ?? context.filename

    if (isExemptFile(filename)) {
      return {}
    }

    return {
      Literal(node) {
        if (typeof node.value !== 'string') {
          return
        }

        if (isDocUrl(node.value)) {
          context.report({
            node,
            messageId: 'noHardcodedDocUrl',
          })
        }
      },

      TemplateLiteral(node) {
        // Only check fully static template literals (no expressions).
        // Dynamic templates like `${base}/path` cannot be statically evaluated.
        if (node.expressions.length === 0) {
          const cooked = node.quasis[0]?.value.cooked ?? ''
          if (isDocUrl(cooked)) {
            context.report({
              node,
              messageId: 'noHardcodedDocUrl',
            })
          }
        }
      },
    }
  },
}
