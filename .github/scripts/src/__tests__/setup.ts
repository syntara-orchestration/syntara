import { beforeAll, afterEach, afterAll } from 'vitest'
import { http, HttpResponse } from 'msw/http'
import { setupServer } from 'msw/node'

/** Default Slack webhook handler used by notification tests. */
export const handlers = [
  // Slack webhook (using example.com to avoid triggering security scanners)
  http.post('https://hooks.example.com/*', () => {
    return HttpResponse.text('ok')
  }),
]

export const server = setupServer(...handlers)

beforeAll(() => {
  server.listen({ onUnhandledFrame: 'error' })
})

afterEach(() => {
  server.resetHandlers()
})

afterAll(() => server.close())
