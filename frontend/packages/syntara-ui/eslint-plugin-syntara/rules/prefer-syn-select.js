/** @type {import('eslint').Rule.RuleModule} */
export default {
  meta: {
    type: 'suggestion',
    docs: {
      description:
        'Flag importing PatternFly Select. Use <SynSelect> instead so scrollable-menu defaults stay consistent.',
    },
    messages: {
      preferSynSelect:
        'Use SynSelect instead of importing Select from @patternfly/react-core. SynSelect applies scrollable-menu defaults (isScrollable, maxMenuHeight, preventOverflow) and closes on outer scroll. See src/components/SynSelect.tsx. SelectList, SelectOption, SelectGroup, and MenuToggle still come from PatternFly.',
    },
    schema: [],
  },
  create(context) {
    const filename = context.filename.replaceAll('\\', '/')
    if (filename.endsWith('/SynSelect.tsx')) {
      return {}
    }

    /**
     * @param {import('estree').ImportSpecifier} specifier
     * @returns {string | null}
     */
    function getImportedName(specifier) {
      const imported = specifier.imported
      if (imported.type === 'Identifier') {
        return imported.name
      }
      return null
    }

    return {
      ImportDeclaration(node) {
        if (node.source.value !== '@patternfly/react-core') return
        if (node.importKind === 'type') return

        for (const specifier of node.specifiers) {
          if (specifier.type !== 'ImportSpecifier') continue
          if (specifier.importKind === 'type') continue
          if (getImportedName(specifier) === 'Select') {
            context.report({ node: specifier, messageId: 'preferSynSelect' })
          }
        }
      },
    }
  },
}
