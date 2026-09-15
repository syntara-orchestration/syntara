/** @type {import('eslint').Rule.RuleModule} */
export default {
  meta: {
    type: 'suggestion',
    docs: {
      description:
        'Flag raw Modal + ModalHeader + ModalBody + ModalFooter compositions that look like destructive confirmation dialogs. Use <SynConfirmationDialog> instead.',
    },
    messages: {
      preferConfirmationDialog:
        'This Modal appears to be a destructive confirmation dialog. Use the <SynConfirmationDialog> component instead for consistent UX. See src/components/dialogs/SynConfirmationDialog.tsx.',
    },
    schema: [],
  },
  create(context) {
    /** Local name(s) for the PF Modal import */
    const modalImportNames = new Set()
    let hasSynConfirmationDialogImport = false

    const DESTRUCTIVE_KEYWORDS = /\b(delete|remove|cancel|stop|revoke|unassign|detach|disconnect)\b/i

    /**
     * Recursively walk JSX children depth-first, invoking `callback` on every
     * JSXElement encountered.
     * @param {import('estree-jsx').JSXChild[]} children
     * @param {(element: import('estree-jsx').JSXElement) => void} callback
     */
    function walkJSXChildren(children, callback) {
      for (const child of children) {
        if (child.type === 'JSXElement') {
          callback(child)
          walkJSXChildren(child.children, callback)
        } else if (child.type === 'JSXFragment') {
          walkJSXChildren(child.children, callback)
        }
      }
    }

    /**
     * Extract a plain string value from a JSX attribute value node.
     * Handles `StringLiteral` (`title="Delete"`) and
     * `JSXExpressionContainer` wrapping a string literal (`title={"Delete"}`).
     * Returns `null` for dynamic expressions.
     * @param {import('estree-jsx').JSXAttribute['value']} valueNode
     * @returns {string | null}
     */
    function getStaticStringValue(valueNode) {
      if (!valueNode) return null
      if (valueNode.type === 'Literal' && typeof valueNode.value === 'string') {
        return valueNode.value
      }
      if (
        valueNode.type === 'JSXExpressionContainer' &&
        valueNode.expression.type === 'Literal' &&
        typeof valueNode.expression.value === 'string'
      ) {
        return valueNode.expression.value
      }
      if (
        valueNode.type === 'JSXExpressionContainer' &&
        valueNode.expression.type === 'TemplateLiteral' &&
        valueNode.expression.quasis.length === 1
      ) {
        return valueNode.expression.quasis[0].value.cooked
      }
      return null
    }

    /**
     * Get the element name from a JSXOpeningElement, handling both
     * `JSXIdentifier` (`ModalHeader`) and `JSXMemberExpression` cases.
     * @param {import('estree-jsx').JSXOpeningElement} openingElement
     * @returns {string | null}
     */
    function getElementName(openingElement) {
      if (openingElement.name.type === 'JSXIdentifier') {
        return openingElement.name.name
      }
      return null
    }

    return {
      ImportDeclaration(node) {
        // Track Modal imports from PatternFly
        if (node.source.value === '@patternfly/react-core') {
          for (const specifier of node.specifiers) {
            if (specifier.type === 'ImportSpecifier' && specifier.imported.name === 'Modal') {
              modalImportNames.add(specifier.local.name)
            }
          }
        }

        // Track SynConfirmationDialog imports from any source
        for (const specifier of node.specifiers) {
          const importedName = specifier.type === 'ImportSpecifier' ? specifier.imported.name : specifier.local.name
          if (importedName === 'SynConfirmationDialog') {
            hasSynConfirmationDialogImport = true
          }
        }
      },

      JSXElement(node) {
        // Skip the entire file if SynConfirmationDialog is already imported
        if (hasSynConfirmationDialogImport) return

        const elementName = getElementName(node.openingElement)
        if (!elementName || !modalImportNames.has(elementName)) return

        let hasDestructiveTitle = false
        let hasDangerButton = false

        walkJSXChildren(node.children, (child) => {
          const childName = getElementName(child.openingElement)

          // Check for ModalHeader with a destructive keyword in its title attribute
          if (childName === 'ModalHeader') {
            for (const attr of child.openingElement.attributes) {
              if (attr.type === 'JSXAttribute' && attr.name.name === 'title') {
                const titleValue = getStaticStringValue(attr.value)
                if (titleValue && DESTRUCTIVE_KEYWORDS.test(titleValue)) {
                  hasDestructiveTitle = true
                }
              }
            }
          }

          // Check for Button with variant="danger"
          if (childName === 'Button') {
            for (const attr of child.openingElement.attributes) {
              if (attr.type !== 'JSXAttribute') continue
              if (attr.name.name !== 'variant') continue
              const variantValue = getStaticStringValue(attr.value)
              if (variantValue === 'danger') {
                hasDangerButton = true
              }
            }
          }
        })

        if (hasDestructiveTitle && hasDangerButton) {
          context.report({
            node: node.openingElement,
            messageId: 'preferConfirmationDialog',
          })
        }
      },
    }
  },
}
