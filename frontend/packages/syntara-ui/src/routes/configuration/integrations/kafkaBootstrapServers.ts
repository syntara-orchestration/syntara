const _MAX_BOOTSTRAP_SERVERS = 20
const _MIN_TCP_PORT = 1
const _MAX_TCP_PORT = 65535

/** Split a comma- or newline-separated broker list into trimmed host:port values. */
export function parseBootstrapServers(raw: string): string[] {
  return raw
    .split(/[\n,]/)
    .map((part) => part.trim())
    .filter((part) => part.length > 0)
}

/** Join broker addresses for a multiline form field. */
export function formatBootstrapServers(servers: readonly string[]): string {
  return servers.join('\n')
}

/** Return the first validation error for one broker address, matching the backend parser. */
export function bootstrapServerError(raw: string): string | undefined {
  const value = raw.trim()
  if (!value) return 'A bootstrap server must not be empty.'
  if (/[/?#@\s]/.test(value)) {
    return `Bootstrap server '${value}' must be host:port with no path, query, or userinfo.`
  }

  let host: string
  let portText: string
  if (value.startsWith('[')) {
    const end = value.indexOf(']')
    const portSuffix = end >= 0 ? value.slice(end + 1) : ''
    host = end > 0 ? value.slice(1, end) : ''
    if (!host || !portSuffix.startsWith(':')) {
      return `Bootstrap server '${value}' must use [ipv6]:port.`
    }
    portText = portSuffix.slice(1)
  } else {
    const parts = value.split(':')
    if (parts.length !== 2) return `Bootstrap server '${value}' must be host:port.`
    host = parts[0] ?? ''
    portText = parts[1] ?? ''
  }

  if (!host) return `Bootstrap server '${value}' is missing a host.`
  if (!/^\d+$/.test(portText)) return `Bootstrap server '${value}' has a non-numeric port.`
  const port = Number(portText)
  if (port < _MIN_TCP_PORT || port > _MAX_TCP_PORT) {
    return `Bootstrap server '${value}' has a port outside 1-65535.`
  }
  return undefined
}

/** Return the first validation error for a broker list, or undefined when it is valid. */
export function bootstrapServersFieldError(raw: string): string | undefined {
  const servers = parseBootstrapServers(raw)
  if (servers.length === 0) return 'At least one bootstrap server is required'
  if (servers.length > _MAX_BOOTSTRAP_SERVERS) return 'At most 20 bootstrap servers are allowed'
  for (const server of servers) {
    const error = bootstrapServerError(server)
    if (error) return error
  }
  return undefined
}
