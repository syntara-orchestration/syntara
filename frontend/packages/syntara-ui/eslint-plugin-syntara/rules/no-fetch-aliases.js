/** Checks whether a fetch identifier is used as a property name, not a reference. */
function isNonComputedPropertyName(node) {
  const parent = node.parent
  return parent?.type === 'MemberExpression' && parent.property === node && !parent.computed
}

/** Checks whether an identifier is a binding position rather than a reference. */
function isBindingIdentifier(node) {
  const parent = node.parent
  if (!parent) return true

  return (
    (parent.type === 'VariableDeclarator' && parent.id === node) ||
    (parent.type === 'FunctionDeclaration' && parent.id === node) ||
    (parent.type === 'FunctionExpression' && parent.id === node) ||
    (parent.type === 'ArrowFunctionExpression' && parent.id === node) ||
    (parent.type === 'ClassDeclaration' && parent.id === node) ||
    (parent.type === 'ClassExpression' && parent.id === node) ||
    (parent.type === 'CatchClause' && parent.param === node) ||
    (parent.type === 'RestElement' && parent.argument === node) ||
    (parent.type === 'AssignmentPattern' && parent.left === node)
  )
}

/** Checks whether a fetch identifier is an import/export name or object key. */
function isNameOnlyIdentifier(node) {
  const parent = node.parent
  if (!parent) return true

  if (parent.type === 'ImportSpecifier' || parent.type === 'ExportSpecifier') return true
  if (parent.type === 'TSPropertySignature' || parent.type === 'TSMethodSignature') return parent.key === node

  return parent.type === 'Property' && parent.key === node && !parent.method && !parent.shorthand && !parent.computed
}

/** Checks whether fetch resolves to a local binding instead of the browser global. */
function isLocallyDeclared(context, node) {
  let scope = context.sourceCode.getScope(node)
  while (scope) {
    const variable = scope.set.get('fetch')
    if (variable?.defs.length) return true
    scope = scope.upper
  }
  return false
}

/** Checks whether the shared HTTP rule already handles this direct call. */
function isDirectFetchCall(node) {
  const parent = node.parent
  return parent?.type === 'CallExpression' && parent.callee === node
}

export default {
  meta: {
    type: 'problem',
    docs: {
      description: 'Disallow aliasing or passing the global fetch function instead of using a typed API client.',
    },
    messages: {
      noFetchAlias: 'Do not alias or pass global fetch. Use a typed API client instead.',
    },
    schema: [],
  },

  create(context) {
    return {
      Identifier(node) {
        if (
          node.name !== 'fetch' ||
          isNonComputedPropertyName(node) ||
          isBindingIdentifier(node) ||
          isNameOnlyIdentifier(node) ||
          isLocallyDeclared(context, node) ||
          isDirectFetchCall(node)
        ) {
          return
        }

        context.report({ node, messageId: 'noFetchAlias' })
      },
    }
  },
}
