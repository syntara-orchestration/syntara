import { describe, expect, it } from 'vitest'

import {
  EXECUTIONS_LIST_LOAD_DEFAULT_MESSAGE,
  EXECUTIONS_LIST_LOAD_FORBIDDEN_MESSAGE,
  EXECUTIONS_LIST_LOAD_UNAVAILABLE_MESSAGE,
  getExecutionsListLoadErrorMessage,
} from './executionsListLoadErrors'

describe('getExecutionsListLoadErrorMessage', () => {
  it('maps 403 to a permission message', () => {
    expect(getExecutionsListLoadErrorMessage({ status: 403, detail: 'Forbidden' })).toBe(
      EXECUTIONS_LIST_LOAD_FORBIDDEN_MESSAGE
    )
  })

  it('maps forbidden codes and message heuristics to the permission message', () => {
    expect(getExecutionsListLoadErrorMessage({ code: 'FORBIDDEN' })).toBe(EXECUTIONS_LIST_LOAD_FORBIDDEN_MESSAGE)
    expect(getExecutionsListLoadErrorMessage({ detail: 'not authorized for this project' })).toBe(
      EXECUTIONS_LIST_LOAD_FORBIDDEN_MESSAGE
    )
  })

  it('maps 503 to a temporary unavailability message', () => {
    expect(getExecutionsListLoadErrorMessage({ status: 503, detail: 'down' })).toBe(
      EXECUTIONS_LIST_LOAD_UNAVAILABLE_MESSAGE
    )
  })

  it('maps temporal unavailable codes to the unavailability message', () => {
    expect(getExecutionsListLoadErrorMessage({ code: 'TEMPORAL_UNAVAILABLE' })).toBe(
      EXECUTIONS_LIST_LOAD_UNAVAILABLE_MESSAGE
    )
  })

  it('uses an actionable default for other failures', () => {
    expect(getExecutionsListLoadErrorMessage({ status: 500, detail: 'boom' })).toBe(
      EXECUTIONS_LIST_LOAD_DEFAULT_MESSAGE
    )
    expect(getExecutionsListLoadErrorMessage({ message: 'Failed to load' })).toBe(EXECUTIONS_LIST_LOAD_DEFAULT_MESSAGE)
    expect(getExecutionsListLoadErrorMessage(null)).toBe(EXECUTIONS_LIST_LOAD_DEFAULT_MESSAGE)
  })
})
