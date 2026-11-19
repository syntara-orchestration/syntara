const HTTP_CLIENT_RULE_IDS = new Set(['@ansible/no-unapproved-http-client', 'no-unapproved-http-client'])
const DISABLE_DIRECTIVE = /^eslint-disable(?:-(?:next-)?line)?(?:\s+|$)(.*)$/u

/** Parses an HTTP-client disable directive and returns its explanation, if any. */
function parseDirectiveLine(line) {
  const normalized = line
    .trim()
    .replace(/^\*\s?/u, '')
    .trim()
  const match = normalized.match(DISABLE_DIRECTIVE)
  if (!match) return null

  const [ruleList, ...reasonParts] = match[1].split('--')
  const ruleIds = ruleList
    .split(',')
    .map((ruleId) => ruleId.trim())
    .filter(Boolean)

  if (!ruleIds.some((ruleId) => HTTP_CLIENT_RULE_IDS.has(ruleId))) return null

  return { reason: reasonParts.join('--').trim() }
}

/** Reads directives from line and block comments. */
function getDirectives(comment) {
  return comment.value.split(/\r?\n/u).map(parseDirectiveLine).filter(Boolean)
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
        for (const comment of context.sourceCode.getAllComments()) {
          if (getDirectives(comment).some(({ reason }) => !reason)) {
            context.report({ loc: comment.loc, messageId: 'missingReason' })
          }
        }
      },
    }
  },
}
