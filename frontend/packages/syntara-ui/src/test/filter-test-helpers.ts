import { expect } from 'vitest'
import type { Mock } from 'vitest'

/**
 * Test helpers for URL parameter and filter testing
 *
 * These utilities help verify that components correctly update URL search parameters
 * when filters are applied, providing a consistent way to test server-side filtering
 * across different list pages.
 *
 * @see ../../docs/TEST_HELPERS_FILTER_TESTING.md - Comprehensive usage guide with examples for all list pages
 *
 * @example
 * ```typescript
 * it('applies name filter to URL params', async () => {
 *   // ... user interaction ...
 *   await waitFor(() => {
 *     assertUrlParam(mockSetSearchParams, 'name[contains]', 'test')
 *   })
 * })
 * ```
 */

/**
 * Gets the most recent URLSearchParams from a mocked setSearchParams function
 *
 * @param mockSetSearchParams - Vitest mock of the setSearchParams function from the useSearchParams hook
 * @returns The URLSearchParams from the most recent call, or undefined if never called
 *
 * @example
 * ```typescript
 * const params = getLastSearchParams(mockSetSearchParams)
 * expect(params?.get('name[contains]')).toBe('test')
 * ```
 */
export function getLastSearchParams(mockSetSearchParams: Mock): URLSearchParams | undefined {
  const calls = mockSetSearchParams.mock.calls
  if (calls.length === 0) {
    return undefined
  }
  return calls[calls.length - 1][0] as URLSearchParams
}

/**
 * Asserts that a specific URL parameter was set to an expected value
 *
 * This helper combines getting the last search params with an assertion,
 * providing clear error messages when the assertion fails.
 *
 * @param mockSetSearchParams - Vitest mock of the setSearchParams function
 * @param key - The URL parameter key to check
 * @param expectedValue - The expected value for the parameter
 *
 * @throws {Error} If setSearchParams was never called
 * @throws {AssertionError} If the parameter value doesn't match expected
 *
 * @example
 * ```typescript
 * // Verify filter parameter was set correctly
 * await waitFor(() => {
 *   assertUrlParam(mockSetSearchParams, 'name[contains]', 'test')
 * })
 *
 * // Verify pagination cursor was reset
 * await waitFor(() => {
 *   assertUrlParamIsNull(mockSetSearchParams, 'cursor')
 * })
 * ```
 */
export function assertUrlParam(mockSetSearchParams: Mock, key: string, expectedValue: string): void {
  const params = getLastSearchParams(mockSetSearchParams)

  expect(params).toBeDefined()
  expect(params?.get(key)).toBe(expectedValue)
}

/**
 * Asserts that a specific URL parameter is null (not present in URL)
 *
 * Useful for verifying that parameters like pagination cursors are reset
 * when filters change.
 *
 * @param mockSetSearchParams - Vitest mock of the setSearchParams function
 * @param key - The URL parameter key to check
 *
 * @throws {Error} If setSearchParams was never called
 * @throws {AssertionError} If the parameter is not null
 *
 * @example
 * ```typescript
 * // Verify cursor was reset when filter changed
 * await waitFor(() => {
 *   assertUrlParamIsNull(mockSetSearchParams, 'cursor')
 * })
 * ```
 */
export function assertUrlParamIsNull(mockSetSearchParams: Mock, key: string): void {
  const params = getLastSearchParams(mockSetSearchParams)

  expect(params).toBeDefined()
  expect(params?.get(key)).toBeNull()
}

/**
 * Asserts that setSearchParams was called at least once
 *
 * Useful as a basic assertion before checking specific parameter values.
 *
 * @param mockSetSearchParams - Vitest mock of the setSearchParams function
 *
 * @throws {AssertionError} If setSearchParams was never called
 *
 * @example
 * ```typescript
 * await waitFor(() => {
 *   assertSearchParamsWasCalled(mockSetSearchParams)
 * })
 * ```
 */
export function assertSearchParamsWasCalled(mockSetSearchParams: Mock): void {
  expect(mockSetSearchParams).toHaveBeenCalled()
}
