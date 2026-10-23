import { describe, expect, it } from 'vitest'

import { FilterOperatorEnum, FilterTypeEnum } from '../../types/filters'

import {
  EXECUTION_TARGET_STATUS_VALUES,
  getExecutionPlaneFilterDefinitions,
  getExecutionTargetEnabledFilterDefinition,
  getExecutionTargetLastRanAtFilterDefinition,
  getExecutionTargetNameFilterDefinition,
  getExecutionTargetStatusFilterDefinition,
} from './executionPlaneFilters'

describe('executionPlaneFilters', () => {
  describe('getExecutionTargetNameFilterDefinition', () => {
    it('returns name filter with CONTAINS', () => {
      const definition = getExecutionTargetNameFilterDefinition()

      expect(definition.key).toBe('name')
      expect(definition.label).toBe('Name')
      expect(definition.type).toBe(FilterTypeEnum.TEXT)
      expect(definition.operators).toEqual([FilterOperatorEnum.CONTAINS])
      expect(definition.defaultOperator).toBe(FilterOperatorEnum.CONTAINS)
      expect(definition.placeholder).toBe('Filter by name')
    })
  })

  describe('getExecutionTargetStatusFilterDefinition', () => {
    it('returns MULTISELECT status filter with IN (Approvals pattern)', () => {
      const definition = getExecutionTargetStatusFilterDefinition()

      expect(definition.key).toBe('status')
      expect(definition.label).toBe('Status')
      expect(definition.type).toBe(FilterTypeEnum.MULTISELECT)
      expect(definition.operators).toEqual([FilterOperatorEnum.IN])
      expect(definition.defaultOperator).toBe(FilterOperatorEnum.IN)
      expect(definition.placeholder).toBe('Filter by status')
    })

    it('lists known execution-target status options', () => {
      const definition = getExecutionTargetStatusFilterDefinition()
      const values = definition.options?.map((o) => o.value) ?? []

      expect(values).toEqual([...EXECUTION_TARGET_STATUS_VALUES])
      expect(definition.options?.[0]?.label).toBe('Registering')
      expect(definition.options?.map((o) => o.value)).toContain('degraded')
      expect(definition.options?.map((o) => o.value)).toContain('bootstrapping')
    })

    it('produces status[in] query key', () => {
      const definition = getExecutionTargetStatusFilterDefinition()
      const operator = definition.defaultOperator ?? 'eq'
      const paramKey = operator === 'eq' ? definition.key : `${definition.key}[${operator}]`
      expect(paramKey).toBe('status[in]')
    })
  })

  describe('getExecutionTargetEnabledFilterDefinition', () => {
    it('returns State SELECT with string true/false options', () => {
      const definition = getExecutionTargetEnabledFilterDefinition()

      expect(definition.key).toBe('enabled')
      expect(definition.label).toBe('State')
      expect(definition.type).toBe(FilterTypeEnum.SELECT)
      expect(definition.options).toEqual([
        { value: 'true', label: 'Enabled' },
        { value: 'false', label: 'Disabled' },
      ])
      expect(definition.placeholder).toBe('Filter by state')
    })
  })

  describe('getExecutionTargetLastRanAtFilterDefinition', () => {
    it('returns Last run DATERANGE with gte/lte', () => {
      const definition = getExecutionTargetLastRanAtFilterDefinition()

      expect(definition.key).toBe('last_ran_at')
      expect(definition.label).toBe('Last run')
      expect(definition.type).toBe(FilterTypeEnum.DATERANGE)
      expect(definition.operators).toEqual([FilterOperatorEnum.GTE, FilterOperatorEnum.LTE])
      expect(definition.placeholder).toBe('Filter by last run')
    })
  })

  describe('getExecutionPlaneFilterDefinitions', () => {
    it('returns name, status, state, and last run in attribute order', () => {
      const definitions = getExecutionPlaneFilterDefinitions()
      expect(definitions.map((d) => d.key)).toEqual(['name', 'status', 'enabled', 'last_ran_at'])
    })
  })
})
