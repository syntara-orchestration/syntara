import picomatch from 'picomatch'

/**
 * @param {import('eslint').Rule.RuleContext} context
 * @param {string[]} allowedFiles
 */
function isAllowedFile(context, allowedFiles) {
  if (allowedFiles.length === 0) {
    return false
  }

  const filename = context.physicalFilename ?? context.filename
  const normalized = filename.replace(/\\/g, '/')
  // dot: true so **/globs still match when the absolute path includes a
  // hidden segment (e.g. ~/.cursor/worktrees/... during local worktrees).
  return allowedFiles.some((pattern) => picomatch(pattern, { dot: true })(normalized))
}

/** @type {import('eslint').Rule.RuleModule} */
export default {
  meta: {
    type: 'problem',
    docs: {
      description:
        'Disallow raw Date locale methods, and restrict PatternFly Timestamp imports to the canonical wrapper components (DateCell/UserTimestamp/ExecutionTimestamp) so date/time display stays consistent across the UI.',
      recommended: true,
    },
    messages: {
      noLocaleDate:
        'Use DateCell/UserTimestamp/ExecutionTimestamp (which wrap PatternFly Timestamp) instead of {{ method }}(). Raw locale methods bypass the shared dateFormat/timeFormat config. See dateUtils.ts for the small set of plain-string helpers still allowed outside JSX contexts.',
      restrictedTimestampImport:
        'Import Timestamp only from DateCell, UserTimestamp, or ExecutionTimestamp instead of `@patternfly/react-core` directly, so every date/time display shares the same dateFormat/timeFormat. Use <DateCell dateString={...} /> (or <UserTimestamp .../>, <ExecutionTimestamp .../>) instead.',
    },
    schema: [
      {
        type: 'object',
        properties: {
          allowedFiles: {
            type: 'array',
            items: { type: 'string' },
            description:
              'Glob patterns for files allowed to import PatternFly Timestamp directly (the canonical wrapper components) and to use raw locale Date methods (e.g. dateUtils.ts).',
          },
        },
        additionalProperties: false,
      },
    ],
  },
  create(context) {
    const options = context.options[0] ?? {}
    const allowedFiles = options.allowedFiles ?? []

    if (isAllowedFile(context, allowedFiles)) {
      return {}
    }

    return {
      CallExpression(node) {
        if (node.callee.type !== 'MemberExpression' || node.callee.property.type !== 'Identifier') {
          return
        }
        const method = node.callee.property.name

        if (method === 'toLocaleDateString' || method === 'toLocaleTimeString') {
          context.report({ node, messageId: 'noLocaleDate', data: { method } })
          return
        }

        if (method === 'toLocaleString') {
          const obj = node.callee.object
          if (obj.type === 'NewExpression' && obj.callee.type === 'Identifier' && obj.callee.name === 'Date') {
            context.report({ node, messageId: 'noLocaleDate', data: { method } })
          }
        }
      },

      ImportDeclaration(node) {
        if (node.source.value !== '@patternfly/react-core') {
          return
        }
        for (const specifier of node.specifiers) {
          if (specifier.type === 'ImportSpecifier' && specifier.imported.name === 'Timestamp') {
            context.report({ node: specifier, messageId: 'restrictedTimestampImport' })
          }
        }
      },
    }
  },
}
