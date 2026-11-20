const HTTP_CLIENT_RULE_IDS = new Set(['@ansible/no-unapproved-http-client', 'no-unapproved-http-client'])

/** Checks whether an ESLint disable directive includes the shared HTTP rule. */
function disablesHttpClientRule(directive) {
  const ruleIds = directive.value
    .split(',')
    .map((ruleId) => ruleId.trim())
    .filter(Boolean)

  // A directive without rule IDs suppresses every rule, including the HTTP-client rule.
  return ruleIds.length === 0 || ruleIds.some((ruleId) => HTTP_CLIENT_RULE_IDS.has(ruleId))
}

export default {
  meta: {
    type: 'problem',
    docs: {
      description: 'Require an explanation when disabling the shared HTTP-client rule.',
    },
    messages: {
      missingReason:
        'HTTP-client rule disables must include a short explanation after "--" so the exception remains reviewable.',
    },
    schema: [],
  },

  create(context) {
    return {
      Program() {
        const { directives } = context.sourceCode.getDisableDirectives()

        for (const directive of directives) {
          if (
            !directive.type.startsWith('disable') ||
            !disablesHttpClientRule(directive) ||
            directive.justification.trim()
          ) {
            continue
          }

          context.report({ loc: directive.node.loc, messageId: 'missingReason' })
        }
      },
    }
  },
}
