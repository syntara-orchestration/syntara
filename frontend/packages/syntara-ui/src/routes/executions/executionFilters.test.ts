import { describe, expect, it, vi, beforeEach } from 'vitest'

import { createFilterChangeHandler } from '../../hooks/useFilterChangeHandler'
import { FilterTypeEnum } from '../../types/filters'

import {
  EXECUTION_STATUS_APPROVAL_PENDING,
  getExecutionWorkflowFilterDefinition,
  getExecutionStatusFilterDefinition,
  getExecutionCreatedAtFilterDefinition,
  transformExecutionStatusFilter,
  transformWorkflowsToOptions,
} from './executionFilters'

describe('executionFilters', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('getExecutionWorkflowFilterDefinition', () => {
    it('returns workflow filter definition with correct configuration', () => {
      const definition = getExecutionWorkflowFilterDefinition()

      expect(definition.key).toBe('workflow_id')
      expect(definition.label).toBe('Workflow name')
      expect(definition.type).toBe(FilterTypeEnum.SELECT)
      expect(definition.placeholder).toBe('Search workflows')
    })

    it('uses async options for server-side typeahead', () => {
      const definition = getExecutionWorkflowFilterDefinition()

      // Workflow filter uses async options instead of static options
      expect(definition.asyncOptions).toBeDefined()
      expect(definition.options).toBeUndefined()
    })

    it('uses exact match query parameter without operator', () => {
      const definition = getExecutionWorkflowFilterDefinition()

      // Workflow filter uses exact match (no operator)
      expect(definition.operators).toBeUndefined()
      expect(definition.defaultOperator).toBeUndefined()

      // This produces 'workflow_id=value' not 'workflow_id[eq]=value' for backend API
    })

    it('asyncOptions is an async function', () => {
      const definition = getExecutionWorkflowFilterDefinition()

      // Verify it's an async function
      expect(definition.asyncOptions).toBeInstanceOf(Function)
      expect(definition.asyncOptions!('test')).toBeInstanceOf(Promise)
    })

    it('asyncOptions handles search parameter correctly', async () => {
      // We can't easily mock openapi-fetch, but we can test the function behavior
      // by verifying it returns a promise and handles the searchValue parameter
      const definition = getExecutionWorkflowFilterDefinition()

      // Test with search value
      const resultWithSearch = definition.asyncOptions!('test-search')
      expect(resultWithSearch).toBeInstanceOf(Promise)

      // Test with empty search value
      const resultWithoutSearch = definition.asyncOptions!('')
      expect(resultWithoutSearch).toBeInstanceOf(Promise)

      // Test with whitespace-only search value
      const resultWithWhitespace = definition.asyncOptions!('   ')
      expect(resultWithWhitespace).toBeInstanceOf(Promise)

      // All should resolve to arrays (even if empty due to network issues in test)
      const [r1, r2, r3] = await Promise.all([resultWithSearch, resultWithoutSearch, resultWithWhitespace])
      expect(Array.isArray(r1)).toBe(true)
      expect(Array.isArray(r2)).toBe(true)
      expect(Array.isArray(r3)).toBe(true)
    })
  })

  describe('getExecutionStatusFilterDefinition', () => {
    it('returns status filter definition with correct configuration', () => {
      const definition = getExecutionStatusFilterDefinition()

      expect(definition.key).toBe('status')
      expect(definition.label).toBe('Status')
      expect(definition.type).toBe(FilterTypeEnum.SELECT)
      expect(definition.placeholder).toBe('Filter by status')
    })

    it('provides all valid execution status options from API contract', () => {
      const definition = getExecutionStatusFilterDefinition()

      expect(definition.options).toBeDefined()
      const statusValues = definition.options!.map((o) => o.value)

      // Values derived from ExecutionStatusEnum in @syntara/contracts
      expect(statusValues).toEqual([
        'pending',
        'running',
        'paused',
        'completed',
        'completed_with_errors',
        'failed',
        'cancelled',
        EXECUTION_STATUS_APPROVAL_PENDING,
      ])
    })

    it('provides human-readable labels for status values', () => {
      const definition = getExecutionStatusFilterDefinition()

      const statusLabels = definition.options!.map((o) => o.label)

      expect(statusLabels).toEqual([
        'Pending',
        'Running',
        'Paused',
        'Completed',
        'Completed with errors',
        'Failed',
        'Cancelled',
        'Pending approval',
      ])
    })

    it('uses exact match query parameter without operator', () => {
      const definition = getExecutionStatusFilterDefinition()

      // Status filter uses exact match (no operator)
      expect(definition.operators).toBeUndefined()
      expect(definition.defaultOperator).toBeUndefined()

      // This produces 'status=value' not 'status[eq]=value' for backend API
    })
  })

  describe('transformWorkflowsToOptions', () => {
    it('transforms valid workflows to options', () => {
      const workflows = [
        { id: 'wf-1', name: 'Workflow 1' },
        { id: 'wf-2', name: 'Workflow 2' },
      ]

      const result = transformWorkflowsToOptions(workflows)

      expect(result).toEqual([
        { value: 'wf-1', label: 'Workflow 1' },
        { value: 'wf-2', label: 'Workflow 2' },
      ])
    })

    it('filters out workflows with missing id', () => {
      const workflows = [
        { id: 'wf-1', name: 'Valid' },
        { id: '', name: 'Empty ID' },
        { id: null, name: 'Null ID' },
        { name: 'No ID property' },
      ]

      const result = transformWorkflowsToOptions(workflows)

      expect(result).toEqual([{ value: 'wf-1', label: 'Valid' }])
    })

    it('filters out workflows with missing name', () => {
      const workflows = [
        { id: 'wf-1', name: 'Valid' },
        { id: 'wf-2', name: '' },
        { id: 'wf-3', name: null },
        { id: 'wf-4' },
      ]

      const result = transformWorkflowsToOptions(workflows)

      expect(result).toEqual([{ value: 'wf-1', label: 'Valid' }])
    })

    it('filters out workflows with both id and name missing', () => {
      const workflows = [{ id: 'wf-1', name: 'Valid' }, { id: '', name: '' }, { id: null, name: null }, {}]

      const result = transformWorkflowsToOptions(workflows)

      expect(result).toEqual([{ value: 'wf-1', label: 'Valid' }])
    })

    it('handles empty array', () => {
      const result = transformWorkflowsToOptions([])

      expect(result).toEqual([])
    })

    it('handles array with all invalid workflows', () => {
      const workflows = [{ id: '', name: '' }, { id: null, name: null }, {}]

      const result = transformWorkflowsToOptions(workflows)

      expect(result).toEqual([])
    })
  })

  describe('transformExecutionStatusFilter', () => {
    it('maps Pending approval status selection to approval_pending=true', () => {
      expect(transformExecutionStatusFilter([{ key: 'status', value: EXECUTION_STATUS_APPROVAL_PENDING }])).toEqual([
        { key: 'approval_pending', value: true },
      ])
    })

    it('leaves other status filters unchanged', () => {
      const filters = [{ key: 'status', value: 'completed' }]
      expect(transformExecutionStatusFilter(filters)).toEqual(filters)
    })

    it('leaves non-status filters unchanged', () => {
      const filters = [{ key: 'workflow_id', value: 'workflow-123' }]
      expect(transformExecutionStatusFilter(filters)).toEqual(filters)
    })

    it('maps only pending approval when mixed with other filters', () => {
      expect(
        transformExecutionStatusFilter([
          { key: 'workflow_id', value: 'workflow-123' },
          { key: 'status', value: EXECUTION_STATUS_APPROVAL_PENDING },
        ])
      ).toEqual([
        { key: 'workflow_id', value: 'workflow-123' },
        { key: 'approval_pending', value: true },
      ])
    })

    it('returns empty array for empty input', () => {
      expect(transformExecutionStatusFilter([])).toEqual([])
    })
  })

  describe('createFilterChangeHandler integration', () => {
    it('applies transformExecutionStatusFilter when filters change', () => {
      const setAllFilters = vi.fn()
      const handler = createFilterChangeHandler(null, vi.fn(), vi.fn(), setAllFilters, transformExecutionStatusFilter)

      handler([{ key: 'status', value: EXECUTION_STATUS_APPROVAL_PENDING }])

      expect(setAllFilters).toHaveBeenCalledWith([{ key: 'approval_pending', value: true }])
    })
  })

  describe('getExecutionCreatedAtFilterDefinition', () => {
    it('returns null due to backend limitation', () => {
      const definition = getExecutionCreatedAtFilterDefinition()

      // Currently disabled due to backend OR logic bug
      expect(definition).toBeNull()
    })

    // Tests below are disabled until backend bug is fixed
    // When backend supports AND logic for date ranges, uncomment these tests
    // and update getExecutionCreatedAtFilterDefinition to return the filter definition

    // it('returns created_at filter definition with correct configuration', () => {
    //   const definition = getExecutionCreatedAtFilterDefinition()
    //   expect(definition.key).toBe('created_at')
    //   expect(definition.label).toBe('Created Date')
    //   expect(definition.type).toBe(FilterTypeEnum.DATERANGE)
    //   expect(definition.placeholder).toBe('Filter by creation date')
    // })

    // it('uses GTE and LTE operators for date range', () => {
    //   const definition = getExecutionCreatedAtFilterDefinition()
    //   expect(definition.operators).toEqual([FilterOperatorEnum.GTE, FilterOperatorEnum.LTE])
    // })

    // it('generates correct API query parameter format for date ranges', () => {
    //   const definition = getExecutionCreatedAtFilterDefinition()
    //   expect(definition.operators).toContain(FilterOperatorEnum.GTE)
    //   expect(definition.operators).toContain(FilterOperatorEnum.LTE)
    // })
  })
})
