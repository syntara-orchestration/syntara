// RFC 3986 URI-reference grammar. WHATWG URL alone also accepts spaces and repairs
// malformed references, so use it only to validate the IPv6 address production.
const uriCharacter = "[a-zA-Z0-9._~!$&'()*+,;=\\-]"
const encodedCharacter = `(?:${uriCharacter}|%[a-fA-F0-9]{2})`
const pathCharacter = `(?:${encodedCharacter}|[:@])`
const pathPattern = new RegExp(`^(?:${pathCharacter}|/)*$`)
const queryPattern = new RegExp(`^(?:${pathCharacter}|[/?])*$`)
const schemePattern = /^[a-zA-Z][a-zA-Z0-9+.-]*:/
const authorityPattern = new RegExp(
  `^(?:(?:${encodedCharacter}|:)*@)?(\\[[a-zA-Z0-9:._~!$&'()*+,;=\\-]+\\]|${encodedCharacter}*)(?::[0-9]*)?$`
)
const ipvFuturePattern = new RegExp(`^v[a-f0-9]+\\.(?:${uriCharacter}|:)+$`, 'i')

function validAuthority(value: string): boolean {
  const match = authorityPattern.exec(value)
  if (!match) return false
  const host = match[1] ?? ''
  if (!host.startsWith('[')) return true
  if (ipvFuturePattern.test(host.slice(1, -1))) return true
  try {
    new URL(`http://${host}`)
    return true
  } catch {
    return false
  }
}

/** Validate absolute and relative URI references without normalizing their text. */
export function isUriReference(value: string): boolean {
  const [beforeFragment = '', fragment = '', ...extraFragments] = value.split('#')
  if (extraFragments.length > 0 || !queryPattern.test(fragment)) return false
  const queryIndex = beforeFragment.indexOf('?')
  const path = queryIndex < 0 ? beforeFragment : beforeFragment.slice(0, queryIndex)
  if (queryIndex >= 0 && !queryPattern.test(beforeFragment.slice(queryIndex + 1))) return false
  const scheme = schemePattern.exec(path)
  const rest = scheme ? path.slice(scheme[0].length) : path
  if (rest.startsWith('//')) {
    const slash = rest.indexOf('/', 2)
    return slash < 0
      ? validAuthority(rest.slice(2))
      : validAuthority(rest.slice(2, slash)) && pathPattern.test(rest.slice(slash))
  }
  if (!scheme && (rest.split('/')[0] ?? '').includes(':')) return false
  return pathPattern.test(rest)
}
