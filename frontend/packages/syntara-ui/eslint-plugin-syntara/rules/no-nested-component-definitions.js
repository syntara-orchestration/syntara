/**
 * ESLint rule: no-nested-component-definitions
 *
 * Enforces frontend/AGENTS.md + coding standards §18 (Sonar S6478):
 * "No nested React components — do not declare components inside another component."
 *
 * React identifies a component by its function reference. When a component is
 * (re)created inside a parent function body, React sees a *new* type on every
 * render and unmounts + remounts the entire subtree, destroying all local state
 * and causing unnecessary DOM churn.
 *
 * Detected patterns
 * -----------------
 * ❌  Arrow function assigned to an uppercase variable inside a function body
 *       function MyComponent() {
 *         const Toggle = () => <Button />   // flagged
 *       }
 *
 * ❌  Function declaration with an uppercase name inside a function body
 *       function MyComponent() {
 *         function Dialog() { return <Modal /> }  // flagged
 *       }
 *
 * NOT flagged
 * -----------
 * ✅  Same patterns at module scope (no function ancestor)
 * ✅  Lowercase helpers (not a React component by convention)
 * ✅  Test files (*.test.tsx, *.test.ts, *.spec.tsx, *.spec.ts) — wrapper
 *     components defined in tests are idiomatic and intentional
 */

/**
 * AST node types that constitute a function boundary.
 * Hoisted to module scope so it is allocated once, not once per AST node visit.
 */
const FUNCTION_TYPES = new Set(['FunctionDeclaration', 'FunctionExpression', 'ArrowFunctionExpression'])

/** @type {import('eslint').Rule.RuleModule} */
export default {
  meta: {
    type: 'problem',
    docs: {
      description:
        'Disallow React component definitions inside other functions or components (Sonar S6478). ' +
        'Nested components are re-created on every render, causing React to unmount and remount ' +
        'the entire subtree. Move the component to module scope and pass data as props.',
      recommended: true,
    },
    messages: {
      noNestedComponentDefinition:
        "Do not define React components inside other components or functions. '{{name}}' is defined " +
        'inside a function — move it to module scope and pass data as props.',
    },
    schema: [],
  },

  create(context) {
    // Skip test files and test utility directories — wrapper components are intentional there.
    const filename = (context.physicalFilename ?? context.filename).replace(/\\/g, '/')
    if (/\.(test|spec)\.[jt]sx?$/.test(filename) || /\/(test|test-utils|__tests__)\//.test(filename)) {
      return {}
    }

    /**
     * Returns true when `name` looks like a React component (starts with an
     * uppercase ASCII letter). /^[A-Z]/ is a superset of the previous
     * `name[0] === name[0].toUpperCase()` check (which also matched digits and
     * symbols), so the redundant condition has been removed.
     *
     * @param {string | null | undefined} name
     * @returns {boolean}
     */
    function isComponentName(name) {
      return typeof name === 'string' && /^[A-Z]/.test(name)
    }

    /**
     * Returns true when the node has at least one function-type ancestor that
     * is NOT the outermost Program node — i.e. the node lives inside a function
     * body rather than at module scope.
     *
     * Ancestor node types that count as "inside a function":
     *   FunctionDeclaration, FunctionExpression, ArrowFunctionExpression
     *
     * @param {import('eslint').Rule.Node} node
     * @returns {boolean}
     */
    function isInsideFunction(node) {
      const ancestors = context.getAncestors ? context.getAncestors() : context.sourceCode.getAncestors(node)
      return ancestors.some((ancestor) => FUNCTION_TYPES.has(ancestor.type))
    }

    return {
      /**
       * Catch:  const Toggle = () => <Foo />
       *         const Toggle = function() { return <Foo /> }
       *
       * A VariableDeclarator whose `init` is a function expression (arrow or
       * regular) and whose `id` is an Identifier with an uppercase name.
       */
      VariableDeclarator(node) {
        if (node.id.type !== 'Identifier') return
        if (!isComponentName(node.id.name)) return

        const init = node.init
        if (!init) return
        if (init.type !== 'ArrowFunctionExpression' && init.type !== 'FunctionExpression') return

        if (isInsideFunction(node)) {
          context.report({
            node,
            messageId: 'noNestedComponentDefinition',
            data: { name: node.id.name },
          })
        }
      },

      /**
       * Catch:  function Dialog() { return <Modal /> }
       *
       * A FunctionDeclaration with an uppercase `id.name`.
       */
      FunctionDeclaration(node) {
        if (!node.id) return
        if (!isComponentName(node.id.name)) return

        if (isInsideFunction(node)) {
          context.report({
            node,
            messageId: 'noNestedComponentDefinition',
            data: { name: node.id.name },
          })
        }
      },
    }
  },
}
