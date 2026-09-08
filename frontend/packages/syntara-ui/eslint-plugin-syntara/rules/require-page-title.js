/** @type {import('eslint').Rule.RuleModule} */
export default {
  meta: {
    type: 'suggestion',
    docs: {
      description: 'Require a <title> element in page components for browser tab titles',
    },
    messages: {
      missingTitle:
        'Page components must render a <title> element for the browser tab. ' +
        'Use: <SynPageTitle segments={["Page Name"]} />. ' +
        'Import SynPageTitle from src/components/SynPageTitle.',
    },
    schema: [],
  },
  create(context) {
    let hasTitleElement = false
    let hasDefaultExport = false
    return {
      JSXOpeningElement(node) {
        if (node.name.type === 'JSXIdentifier' && (node.name.name === 'title' || node.name.name === 'SynPageTitle')) {
          hasTitleElement = true
        }
      },
      ExportDefaultDeclaration() {
        hasDefaultExport = true
      },
      'Program:exit'(node) {
        if (hasDefaultExport && !hasTitleElement) {
          // Report on the first statement (not Program) so file-level
          // /* eslint-disable */ directives still apply after ESLint 10's
          // Program.range spans the entire source text.
          context.report({ node: node.body[0] ?? node, messageId: 'missingTitle' })
        }
      },
    }
  },
}
