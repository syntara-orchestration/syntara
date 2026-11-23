import ts from 'typescript'

const SUPPRESSION_RULE_ID = 'syntara/require-http-client-disable-reason'

export function isForbiddenDisable(commentValue) {
  const normalized = commentValue
    .split(/\r?\n/u)
    .map((line) =>
      line
        .trim()
        .replace(/^\*\s?/u, '')
        .trim()
    )
    .filter(Boolean)
    .join(' ')
  const match = normalized.match(/^eslint-disable(?:-(?:next-)?line)?(?:\s+|$)([\s\S]*)$/u)
  if (!match) return false

  const [ruleList] = match[1].split('--')
  const ruleIds = ruleList
    .split(',')
    .map((ruleId) => ruleId.trim())
    .filter(Boolean)

  return ruleIds.length === 0 || ruleIds.includes(SUPPRESSION_RULE_ID)
}

export function findForbiddenDisableLines(source, filePath) {
  const languageVariant = /\.(?:jsx|tsx)$/u.test(filePath) ? ts.LanguageVariant.JSX : ts.LanguageVariant.Standard
  const scanner = ts.createScanner(ts.ScriptTarget.Latest, false, languageVariant, source)
  const findings = []

  while (true) {
    const token = scanner.scan()
    if (token === ts.SyntaxKind.EndOfFileToken) break
    if (token !== ts.SyntaxKind.SingleLineCommentTrivia && token !== ts.SyntaxKind.MultiLineCommentTrivia) continue

    const comment = scanner.getTokenText()
    const value = token === ts.SyntaxKind.SingleLineCommentTrivia ? comment.slice(2) : comment.slice(2, -2)
    if (!isForbiddenDisable(value)) continue

    const line = source.slice(0, scanner.getTokenPos()).split(/\r\n|\n|\r/u).length
    findings.push(line)
  }

  return findings
}
