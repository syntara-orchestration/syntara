import { describe, it, expect } from 'vitest'

import type { FilterConfig } from '../types/filters'
import {
  isValidFilterOperator,
  isValidFilterType,
  VALID_FILTER_OPERATORS,
  VALID_FILTER_TYPES,
  FilterTypeEnum,
} from '../types/filters'

import { formatDateForApi } from './dateUtils'
import { buildFilterParams, buildLabelParams, parseFiltersFromUrl } from './filterUtils'

describe('filterUtils', () => {
  describe('isValidFilterOperator', () => {
    it('should validate valid filter operators', () => {
      expect(isValidFilterOperator('eq')).toBe(true)
      expect(isValidFilterOperator('contains')).toBe(true)
      expect(isValidFilterOperator('starts_with')).toBe(true)
      expect(isValidFilterOperator('gt')).toBe(true)
      expect(isValidFilterOperator('gte')).toBe(true)
      expect(isValidFilterOperator('lt')).toBe(true)
      expect(isValidFilterOperator('lte')).toBe(true)
      expect(isValidFilterOperator('in')).toBe(true)
    })

    it('should reject invalid filter operators', () => {
      expect(isValidFilterOperator('invalid')).toBe(false)
      expect(isValidFilterOperator('environment')).toBe(false)
      expect(isValidFilterOperator('team')).toBe(false)
      expect(isValidFilterOperator('bad')).toBe(false)
      expect(isValidFilterOperator('')).toBe(false)
    })

    it('should have all operators in VALID_FILTER_OPERATORS', () => {
      expect(VALID_FILTER_OPERATORS).toHaveLength(8)
      expect(VALID_FILTER_OPERATORS).toEqual(
        expect.arrayContaining(['eq', 'contains', 'starts_with', 'gt', 'gte', 'lt', 'lte', 'in'])
      )
    })
  })

  describe('isValidFilterType', () => {
    it('should validate valid filter types', () => {
      expect(isValidFilterType('text')).toBe(true)
      expect(isValidFilterType('select')).toBe(true)
      expect(isValidFilterType('date')).toBe(true)
      expect(isValidFilterType('daterange')).toBe(true)
      expect(isValidFilterType('boolean')).toBe(true)
      expect(isValidFilterType('labels')).toBe(true)
    })

    it('should reject invalid filter types', () => {
      expect(isValidFilterType('invalid')).toBe(false)
      expect(isValidFilterType('number')).toBe(false)
      expect(isValidFilterType('dropdown')).toBe(false)
      expect(isValidFilterType('')).toBe(false)
    })

    it('should have all types in VALID_FILTER_TYPES', () => {
      expect(VALID_FILTER_TYPES).toHaveLength(7)
      expect(VALID_FILTER_TYPES).toEqual(
        expect.arrayContaining(['text', 'select', 'multiselect', 'date', 'daterange', 'boolean', 'labels'])
      )
    })

    it('should validate FilterTypeEnum values', () => {
      expect(isValidFilterType(FilterTypeEnum.TEXT)).toBe(true)
      expect(isValidFilterType(FilterTypeEnum.SELECT)).toBe(true)
      expect(isValidFilterType(FilterTypeEnum.MULTISELECT)).toBe(true)
      expect(isValidFilterType(FilterTypeEnum.DATE)).toBe(true)
      expect(isValidFilterType(FilterTypeEnum.DATERANGE)).toBe(true)
      expect(isValidFilterType(FilterTypeEnum.BOOLEAN)).toBe(true)
      expect(isValidFilterType(FilterTypeEnum.LABELS)).toBe(true)
    })

    it('should validate multiselect as both string and enum', () => {
      expect(isValidFilterType('multiselect')).toBe(true)
      expect(isValidFilterType(FilterTypeEnum.MULTISELECT)).toBe(true)
    })
  })

  describe('buildFilterParams', () => {
    it('should build params for single filter with contains operator', () => {
      const filters: FilterConfig[] = [{ key: 'name', operator: 'contains', value: 'deploy' }]

      const result = buildFilterParams(filters)

      expect(result).toEqual({
        'name[contains]': 'deploy',
      })
    })

    it('should build params for filter without operator (defaults to eq)', () => {
      const filters: FilterConfig[] = [{ key: 'is_enabled', value: true }]

      const result = buildFilterParams(filters)

      expect(result).toEqual({
        is_enabled: true,
      })
    })

    it('should build params for filter with eq operator (no brackets)', () => {
      const filters: FilterConfig[] = [{ key: 'is_enabled', operator: 'eq', value: true }]

      const result = buildFilterParams(filters)

      expect(result).toEqual({
        is_enabled: true,
      })
    })

    it('should build params for filter with starts_with operator', () => {
      const filters: FilterConfig[] = [{ key: 'name', operator: 'starts_with', value: 'prod-' }]

      const result = buildFilterParams(filters)

      expect(result).toEqual({
        'name[starts_with]': 'prod-',
      })
    })

    it('should build params for filter with in operator and array value', () => {
      const filters: FilterConfig[] = [{ key: 'status', operator: 'in', value: ['running', 'pending', 'failed'] }]

      const result = buildFilterParams(filters)

      expect(result).toEqual({
        'status[in]': 'running,pending,failed',
      })
    })

    it('should build params for filter with single value in array (in operator)', () => {
      const filters: FilterConfig[] = [{ key: 'status', operator: 'in', value: ['running'] }]

      const result = buildFilterParams(filters)

      expect(result).toEqual({
        'status[in]': 'running',
      })
    })

    it('should build params for date filter with gte operator', () => {
      const date = new Date('2024-01-01T00:00:00.000Z')
      const filters: FilterConfig[] = [{ key: 'created_at', operator: 'gte', value: date }]

      const result = buildFilterParams(filters)

      expect(result).toEqual({
        'created_at[gte]': '2024-01-01T00:00:00.000Z',
      })
    })

    it('should build params for date filter with lte operator', () => {
      const date = new Date('2024-12-31T23:59:59.999Z')
      const filters: FilterConfig[] = [{ key: 'created_at', operator: 'lte', value: date }]

      const result = buildFilterParams(filters)

      expect(result).toEqual({
        'created_at[lte]': '2024-12-31T23:59:59.999Z',
      })
    })

    it('should build params for date filter with gt operator', () => {
      const date = new Date('2024-06-15T12:30:00.000Z')
      const filters: FilterConfig[] = [{ key: 'updated_at', operator: 'gt', value: date }]

      const result = buildFilterParams(filters)

      expect(result).toEqual({
        'updated_at[gt]': '2024-06-15T12:30:00.000Z',
      })
    })

    it('should build params for date filter with lt operator', () => {
      const date = new Date('2024-03-20T08:00:00.000Z')
      const filters: FilterConfig[] = [{ key: 'updated_at', operator: 'lt', value: date }]

      const result = buildFilterParams(filters)

      expect(result).toEqual({
        'updated_at[lt]': '2024-03-20T08:00:00.000Z',
      })
    })

    it('should build params for multiple filters combined', () => {
      const filters: FilterConfig[] = [
        { key: 'name', operator: 'contains', value: 'deploy' },
        { key: 'is_enabled', value: true },
        { key: 'status', operator: 'in', value: ['running', 'pending'] },
        { key: 'created_at', operator: 'gte', value: new Date('2024-01-01T00:00:00.000Z') },
      ]

      const result = buildFilterParams(filters)

      expect(result).toEqual({
        'name[contains]': 'deploy',
        is_enabled: true,
        'status[in]': 'running,pending',
        'created_at[gte]': '2024-01-01T00:00:00.000Z',
      })
    })

    it('should build params for number value', () => {
      const filters: FilterConfig[] = [{ key: 'count', operator: 'gt', value: 10 }]

      const result = buildFilterParams(filters)

      expect(result).toEqual({
        'count[gt]': 10,
      })
    })

    it('should build params for boolean value', () => {
      const filters: FilterConfig[] = [
        { key: 'is_enabled', value: true },
        { key: 'is_public', value: false },
      ]

      const result = buildFilterParams(filters)

      expect(result).toEqual({
        is_enabled: true,
        is_public: false,
      })
    })

    // Edge cases
    it('should skip filters with null value', () => {
      const filters: FilterConfig[] = [
        { key: 'name', operator: 'contains', value: 'deploy' },
        { key: 'description', operator: 'contains', value: null as unknown as string },
      ]

      const result = buildFilterParams(filters)

      expect(result).toEqual({
        'name[contains]': 'deploy',
      })
    })

    it('should skip filters with undefined value', () => {
      const filters: FilterConfig[] = [
        { key: 'name', operator: 'contains', value: 'deploy' },
        { key: 'description', operator: 'contains', value: undefined as unknown as string },
      ]

      const result = buildFilterParams(filters)

      expect(result).toEqual({
        'name[contains]': 'deploy',
      })
    })

    it('should skip filters with empty string value', () => {
      const filters: FilterConfig[] = [
        { key: 'name', operator: 'contains', value: 'deploy' },
        { key: 'description', operator: 'contains', value: '' },
      ]

      const result = buildFilterParams(filters)

      expect(result).toEqual({
        'name[contains]': 'deploy',
      })
    })

    it('should skip filters with whitespace-only string value', () => {
      const filters: FilterConfig[] = [
        { key: 'name', operator: 'contains', value: 'deploy' },
        { key: 'description', operator: 'contains', value: '   ' },
      ]

      const result = buildFilterParams(filters)

      expect(result).toEqual({
        'name[contains]': 'deploy',
      })
    })

    it('should skip filters with empty array value', () => {
      const filters: FilterConfig[] = [
        { key: 'name', operator: 'contains', value: 'deploy' },
        { key: 'status', operator: 'in', value: [] },
      ]

      const result = buildFilterParams(filters)

      expect(result).toEqual({
        'name[contains]': 'deploy',
      })
    })

    it('should return empty object for empty filters array', () => {
      const result = buildFilterParams([])

      expect(result).toEqual({})
    })

    it('should return empty object when all filters have invalid values', () => {
      const filters: FilterConfig[] = [
        { key: 'name', operator: 'contains', value: '' },
        { key: 'status', operator: 'in', value: [] },
        { key: 'description', value: null as unknown as string },
      ]

      const result = buildFilterParams(filters)

      expect(result).toEqual({})
    })
  })

  describe('formatDateForApi', () => {
    it('should format date to ISO 8601 string', () => {
      const date = new Date('2024-01-01T00:00:00.000Z')

      const result = formatDateForApi(date)

      expect(result).toBe('2024-01-01T00:00:00.000Z')
    })

    it('should format date with time to ISO 8601 string', () => {
      const date = new Date('2024-06-15T12:30:45.678Z')

      const result = formatDateForApi(date)

      expect(result).toBe('2024-06-15T12:30:45.678Z')
    })

    it('should format date at end of day to ISO 8601 string', () => {
      const date = new Date('2024-12-31T23:59:59.999Z')

      const result = formatDateForApi(date)

      expect(result).toBe('2024-12-31T23:59:59.999Z')
    })

    it('should handle timezone correctly (always UTC)', () => {
      // Create date in local timezone
      const date = new Date('2024-01-15T10:30:00')
      // toISOString always returns UTC
      const result = formatDateForApi(date)

      // Result should be in ISO 8601 UTC format
      expect(result).toMatch(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/)
      expect(result).toBe(date.toISOString())
    })

    it('should handle dates with milliseconds', () => {
      const date = new Date('2024-03-20T14:25:33.123Z')

      const result = formatDateForApi(date)

      expect(result).toBe('2024-03-20T14:25:33.123Z')
    })
  })

  describe('buildLabelParams', () => {
    it('should build params for single label', () => {
      const labels = { environment: 'production' }

      const result = buildLabelParams(labels)

      expect(result).toEqual({
        'labels[environment]': 'production',
      })
    })

    it('should build params for multiple labels', () => {
      const labels = {
        environment: 'production',
        team: 'platform',
        region: 'us-east-1',
      }

      const result = buildLabelParams(labels)

      expect(result).toEqual({
        'labels[environment]': 'production',
        'labels[team]': 'platform',
        'labels[region]': 'us-east-1',
      })
    })

    it('should skip labels with empty string values', () => {
      const labels = {
        environment: 'production',
        team: '',
        region: 'us-east-1',
      }

      const result = buildLabelParams(labels)

      expect(result).toEqual({
        'labels[environment]': 'production',
        'labels[region]': 'us-east-1',
      })
    })

    it('should skip labels with whitespace-only values', () => {
      const labels = {
        environment: 'production',
        team: '   ',
        region: 'us-east-1',
      }

      const result = buildLabelParams(labels)

      expect(result).toEqual({
        'labels[environment]': 'production',
        'labels[region]': 'us-east-1',
      })
    })

    it('should return empty object for empty labels', () => {
      const result = buildLabelParams({})

      expect(result).toEqual({})
    })

    it('should return empty object when all labels have empty values', () => {
      const labels = {
        environment: '',
        team: '   ',
      }

      const result = buildLabelParams(labels)

      expect(result).toEqual({})
    })

    it('should handle labels with special characters', () => {
      const labels = {
        'app-name': 'my-app',
        'k8s.io/cluster': 'prod-cluster',
      }

      const result = buildLabelParams(labels)

      expect(result).toEqual({
        'labels[app-name]': 'my-app',
        'labels[k8s.io/cluster]': 'prod-cluster',
      })
    })
  })

  describe('parseFiltersFromUrl', () => {
    it('should parse single filter with operator', () => {
      const searchParams = new URLSearchParams('name[contains]=deploy')

      const result = parseFiltersFromUrl(searchParams)

      expect(result).toEqual([{ key: 'name', operator: 'contains', value: 'deploy' }])
    })

    it('should parse filter without operator (defaults to eq)', () => {
      const searchParams = new URLSearchParams('is_enabled=true')

      const result = parseFiltersFromUrl(searchParams)

      expect(result).toEqual([{ key: 'is_enabled', operator: 'eq', value: 'true' }])
    })

    it('should parse filter with in operator (splits comma-separated values)', () => {
      const searchParams = new URLSearchParams('status[in]=running,pending,failed')

      const result = parseFiltersFromUrl(searchParams)

      expect(result).toEqual([{ key: 'status', operator: 'in', value: ['running', 'pending', 'failed'] }])
    })

    it('should parse multiple filters', () => {
      const searchParams = new URLSearchParams('name[contains]=deploy&is_enabled=true&status[in]=running,failed')

      const result = parseFiltersFromUrl(searchParams)

      expect(result).toEqual([
        { key: 'name', operator: 'contains', value: 'deploy' },
        { key: 'is_enabled', operator: 'eq', value: 'true' },
        { key: 'status', operator: 'in', value: ['running', 'failed'] },
      ])
    })

    it('should parse date filters', () => {
      const searchParams = new URLSearchParams('created_at[gte]=2024-01-01T00:00:00.000Z')

      const result = parseFiltersFromUrl(searchParams)

      expect(result).toEqual([{ key: 'created_at', operator: 'gte', value: '2024-01-01T00:00:00.000Z' }])
    })

    it('should skip label filters (not valid FilterOperator)', () => {
      // Label filters use labels[key]=value syntax where 'key' is not a valid FilterOperator
      // These should be handled separately via buildLabelParams(), not parseFiltersFromUrl()
      const searchParams = new URLSearchParams('labels[environment]=production&labels[team]=platform')

      const result = parseFiltersFromUrl(searchParams)

      // Should return empty array since 'environment' and 'team' are not valid operators
      expect(result).toEqual([])
    })

    it('should skip filters with invalid operators', () => {
      const searchParams = new URLSearchParams('name[invalid]=test&status[in]=running,failed')

      const result = parseFiltersFromUrl(searchParams)

      // Should only include the valid filter (status[in])
      expect(result).toEqual([{ key: 'status', operator: 'in', value: ['running', 'failed'] }])
    })

    it('should skip all filters when all have invalid operators', () => {
      const searchParams = new URLSearchParams('name[bad]=test&field[wrong]=value')

      const result = parseFiltersFromUrl(searchParams)

      expect(result).toEqual([])
    })

    it('should return empty array for empty search params', () => {
      const searchParams = new URLSearchParams('')

      const result = parseFiltersFromUrl(searchParams)

      expect(result).toEqual([])
    })

    it('should skip reserved pagination and sort params', () => {
      const searchParams = new URLSearchParams(
        'sort=-created_at&page=2&perPage=20&cursor=abc&status=failed&history=open&form_prompt=fp-1&approval=ap-1'
      )

      const result = parseFiltersFromUrl(searchParams)

      expect(result).toEqual([{ key: 'status', operator: 'eq', value: 'failed' }])
    })

    it('should skip namespaced sort params so they do not become filter chips', () => {
      // Execution Details uses `activity_sort` alongside Run History filters on the same URL.
      const searchParams = new URLSearchParams('activity_sort=-status&status=completed')

      const result = parseFiltersFromUrl(searchParams)

      expect(result).toEqual([{ key: 'status', operator: 'eq', value: 'completed' }])
    })

    it('should handle URL-encoded values', () => {
      const searchParams = new URLSearchParams('name[contains]=my%20workflow')

      const result = parseFiltersFromUrl(searchParams)

      expect(result).toEqual([{ key: 'name', operator: 'contains', value: 'my workflow' }])
    })

    it('should handle all filter operators', () => {
      const searchParams = new URLSearchParams(
        'name[eq]=exact&desc[contains]=text&title[starts_with]=prefix&count[gt]=10&count[gte]=5&count[lt]=100&count[lte]=50&status[in]=a,b'
      )

      const result = parseFiltersFromUrl(searchParams)

      expect(result).toHaveLength(8)
      expect(result).toContainEqual({ key: 'name', operator: 'eq', value: 'exact' })
      expect(result).toContainEqual({ key: 'desc', operator: 'contains', value: 'text' })
      expect(result).toContainEqual({ key: 'title', operator: 'starts_with', value: 'prefix' })
      expect(result).toContainEqual({ key: 'count', operator: 'gt', value: '10' })
      expect(result).toContainEqual({ key: 'count', operator: 'gte', value: '5' })
      expect(result).toContainEqual({ key: 'count', operator: 'lt', value: '100' })
      expect(result).toContainEqual({ key: 'count', operator: 'lte', value: '50' })
      expect(result).toContainEqual({ key: 'status', operator: 'in', value: ['a', 'b'] })
    })
  })

  describe('parseFiltersFromUrl - malformed bracket inputs and ReDoS protection (S5852)', () => {
    it('should treat a key with "[" but no closing "]" as a plain eq filter', () => {
      // "name[contains=deploy" parses to key="name[contains", value="deploy".
      // The bracket pattern doesn't match (no closing "]"), so it falls through
      // to the eq path — the literal key is passed as-is with operator "eq".
      const searchParams = new URLSearchParams('name[contains=deploy')
      expect(parseFiltersFromUrl(searchParams)).toEqual([{ key: 'name[contains', operator: 'eq', value: 'deploy' }])
    })

    it('should treat a key with empty brackets as a plain eq filter', () => {
      // "name[]" — the regex requires 1+ chars inside brackets, so it does not match;
      // the literal key falls through to the eq path.
      const searchParams = new URLSearchParams('name[]=deploy')
      expect(parseFiltersFromUrl(searchParams)).toEqual([{ key: 'name[]', operator: 'eq', value: 'deploy' }])
    })

    it('should treat a key starting with "[" as a plain eq filter', () => {
      // "[contains]" — [^[]+ requires 1+ non-"[" chars before the bracket;
      // the match fails immediately and the key falls through to the eq path.
      const searchParams = new URLSearchParams('[contains]=deploy')
      expect(parseFiltersFromUrl(searchParams)).toEqual([{ key: '[contains]', operator: 'eq', value: 'deploy' }])
    })

    it('should complete in linear time on pathological inputs (ReDoS guard)', () => {
      // The old regex /^(.+?)\[(.+)\]$/ causes O(n²) backtracking on inputs with
      // many "[" characters and no closing "]": for each "[", the engine exhausts
      // all remaining characters looking for "\]$" before giving up and advancing.
      // The fixed regex uses [^[]+ and [^\]]+ (negated classes) which are O(n).
      const n = 5_000
      const maliciousKey = 'a['.repeat(n) // n "[" characters — triggers O(n²) in old regex
      const searchParams = new URLSearchParams(`${maliciousKey}=value`)

      const start = performance.now()
      parseFiltersFromUrl(searchParams)
      const elapsed = performance.now() - start

      // O(n²) with n=5000 yields ~25M operations; O(n) finishes near-instantly
      expect(elapsed).toBeLessThan(500)
    })
  })

  describe('integration: buildFilterParams and parseFiltersFromUrl', () => {
    it('should round-trip filters correctly', () => {
      const originalFilters: FilterConfig[] = [
        { key: 'name', operator: 'contains', value: 'deploy' },
        { key: 'is_enabled', value: true },
        { key: 'status', operator: 'in', value: ['running', 'failed'] },
      ]

      // Build params
      const params = buildFilterParams(originalFilters)

      // Convert to URLSearchParams
      const searchParams = new URLSearchParams()
      for (const [key, value] of Object.entries(params)) {
        searchParams.set(key, String(value))
      }

      // Parse back
      const parsedFilters = parseFiltersFromUrl(searchParams)

      // Note: boolean values become strings in URL params
      expect(parsedFilters).toEqual([
        { key: 'name', operator: 'contains', value: 'deploy' },
        { key: 'is_enabled', operator: 'eq', value: 'true' },
        { key: 'status', operator: 'in', value: ['running', 'failed'] },
      ])
    })
  })
})
