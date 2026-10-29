const EXEMPT_ELEMENTS = new Set(['SynLink', 'Link', 'TanStackLink'])
const ROUTE_CALLBACK_PROP = /^(?:onClick|onCreate|onEdit|onBack|onReturn)/

function unwrap(node) {
  let current = node
  while (
    current &&
    ['ChainExpression', 'ParenthesizedExpression', 'TSAsExpression', 'TSNonNullExpression', 'TSTypeAssertion'].includes(
      current.type
    )
  ) {
    current = current.expression
  }
  return current
}

function isNavigationCall(node) {
  const expression = unwrap(node)
  if (expression?.type !== 'CallExpression') return false

  const { callee } = expression
  const isNavigate =
    (callee.type === 'Identifier' && callee.name === 'navigate') ||
    (callee.type === 'MemberExpression' && !callee.computed && callee.property.name === 'navigate')
  if (isNavigate) return true

  const isPromiseWrapper = callee.type === 'Identifier' && callee.name === 'detachPromise'
  return isPromiseWrapper && expression.arguments.length === 1 && isNavigationCall(expression.arguments[0])
}

function isNavigationOnlyFunction(node) {
  if (!node) return false
  if (node.type === 'ArrowFunctionExpression' && node.body.type !== 'BlockStatement') {
    return isNavigationCall(node.body)
  }
  if (
    node.type !== 'ArrowFunctionExpression' &&
    node.type !== 'FunctionExpression' &&
    node.type !== 'FunctionDeclaration'
  ) {
    return false
  }

  const statements = node.body.body
  if (statements.length !== 1) return false
  const [statement] = statements
  if (statement.type === 'ExpressionStatement') return isNavigationCall(statement.expression)
  return statement.type === 'ReturnStatement' && isNavigationCall(statement.argument)
}

function resolveFunction(identifier, sourceCode) {
  let scope = sourceCode.getScope(identifier)
  while (scope) {
    const variable = scope.set.get(identifier.name)
    if (variable) {
      const definition = variable.defs[0]?.node
      if (definition?.type === 'FunctionDeclaration') return definition
      if (definition?.type === 'VariableDeclarator') return unwrap(definition.init)
      return undefined
    }
    scope = scope.upper
  }
  return undefined
}

function jsxName(node) {
  if (node.type === 'JSXIdentifier') return node.name
  if (node.type === 'JSXMemberExpression') return jsxName(node.property)
  return undefined
}

/** Flags callback props whose entire job is to navigate; render a SynLink instead. */
export default {
  meta: {
    type: 'problem',
    docs: {
      description: 'Require route navigation to use links instead of callback-driven controls',
    },
    schema: [],
    messages: {
      useLink: 'This callback only navigates. Use a link destination instead of callback-driven navigation.',
    },
  },
  create(context) {
    const sourceCode = context.sourceCode

    return {
      JSXAttribute(attribute) {
        const propName = attribute.name.type === 'JSXIdentifier' ? attribute.name.name : undefined
        if (!propName || !(ROUTE_CALLBACK_PROP.test(propName) || propName === 'addData')) return

        const element = attribute.parent
        const elementName = element?.name ? jsxName(element.name) : undefined
        if (elementName && EXEMPT_ELEMENTS.has(elementName)) return

        const expression =
          attribute.value?.type === 'JSXExpressionContainer' ? unwrap(attribute.value.expression) : null
        const callback = expression?.type === 'Identifier' ? resolveFunction(expression, sourceCode) : expression
        if (isNavigationOnlyFunction(callback)) {
          context.report({ node: attribute, messageId: 'useLink' })
        }
      },
    }
  },
}
