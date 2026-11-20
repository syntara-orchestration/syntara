const GLOBAL_OBJECT_NAMES = new Set(['globalThis', 'window'])

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

/** Checks whether a fetch identifier is an import/export name or property key. */
function isNameOnlyIdentifier(node) {
  const parent = node.parent
  if (!parent) return true

  if (parent.type === 'ImportSpecifier' || parent.type === 'ExportSpecifier') return true
  if (parent.type === 'TSPropertySignature' || parent.type === 'TSMethodSignature') return parent.key === node
  if ((parent.type === 'MethodDefinition' || parent.type === 'PropertyDefinition') && parent.key === node) {
    return !parent.computed
  }

  return parent.type === 'Property' && parent.key === node && !parent.shorthand && !parent.computed
}

/** Checks whether fetch resolves to a local binding instead of the browser global. */
function isLocallyDeclared(context, node, name) {
  let scope = context.sourceCode.getScope(node)
  while (scope) {
    const variable = scope.set.get(name)
    if (variable?.defs.length) return true
    scope = scope.upper
  }
  return false
}

/** Gets a statically known property name from a member or object-pattern property. */
function getStaticPropertyName(node) {
  const property = node.type === 'MemberExpression' ? node.property : node.key
  if (!node.computed && property?.type === 'Identifier') return property.name
  if (node.computed && property?.type === 'Literal' && typeof property.value === 'string') return property.value
  return null
}

/** Checks whether an expression is the unshadowed browser global object. */
function isGlobalObject(context, node, expression) {
  return (
    expression?.type === 'Identifier' &&
    GLOBAL_OBJECT_NAMES.has(expression.name) &&
    !isLocallyDeclared(context, node, expression.name)
  )
}

/** Checks whether a member accesses fetch through the browser global object. */
function isGlobalFetchMember(context, node) {
  return (
    node.type === 'MemberExpression' &&
    isGlobalObject(context, node, node.object) &&
    getStaticPropertyName(node) === 'fetch'
  )
}

/** Checks whether the shared HTTP rule already handles this direct call. */
function isDirectFetchCall(node) {
  const parent = node.parent
  return parent?.type === 'CallExpression' && parent.callee === node
}

/** Finds destructuring that extracts fetch directly from a browser global object. */
function getGlobalFetchPattern(node, context) {
  const parent = node.parent
  let source

  if (parent?.type === 'VariableDeclarator' && parent.id === node) source = parent.init
  if (parent?.type === 'AssignmentExpression' && parent.left === node) source = parent.right

  if (!isGlobalObject(context, node, source)) return []

  return node.properties.filter(
    (property) => property.type === 'Property' && getStaticPropertyName(property) === 'fetch'
  )
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
          isLocallyDeclared(context, node, 'fetch') ||
          isDirectFetchCall(node)
        ) {
          return
        }

        context.report({ node, messageId: 'noFetchAlias' })
      },

      MemberExpression(node) {
        if (!isGlobalFetchMember(context, node) || isDirectFetchCall(node)) return

        context.report({ node, messageId: 'noFetchAlias' })
      },

      ObjectPattern(node) {
        for (const property of getGlobalFetchPattern(node, context)) {
          context.report({ node: property, messageId: 'noFetchAlias' })
        }
      },
    }
  },
}
