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

type WorkflowListResponse = {
  data?: { resources?: Array<{ id?: string | null; name?: string | null }> }
}

const { mockGet } = vi.hoisted(() => ({
  mockGet: vi.fn<(...args: unknown[]) => Promise<WorkflowListResponse>>(),
}))

vi.mock('../../client', () => ({
  workflowFetchClient: {
    GET: (...args: unknown[]) => mockGet(...args),
  },
}))

describe('executionFilters', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockGet.mockResolvedValue({
      data: {
        resources: [
          { id: 'wf-in-project', name: 'In Project Workflow' },
          { id: 'wf-other', name: 'Other Workflow' },
        ],
      },
    })
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

      expect(definition.asyncOptions).toBeInstanceOf(Function)
      expect(definition.asyncOptions!('test')).toBeInstanceOf(Promise)
    })

    it('asyncOptions queries workflows with name search when no project is selected', async () => {
      const definition = getExecutionWorkflowFilterDefinition()

      const options = await definition.asyncOptions!('deploy')

      expect(mockGet).toHaveBeenCalledWith('/workflows', {
        params: {
          query: {
            limit: 50,
            'name[contains]': 'deploy',
          },
        },
      })
      expect(options).toEqual([
        { value: 'wf-in-project', label: 'In Project Workflow' },
        { value: 'wf-other', label: 'Other Workflow' },
      ])
    })

    it('asyncOptions scopes the typeahead query to the selected project', async () => {
      const definition = getExecutionWorkflowFilterDefinition('project-123')

      await definition.asyncOptions!('deploy')

      expect(mockGet).toHaveBeenCalledWith('/workflows', {
        params: {
          query: {
            limit: 50,
            'name[contains]': 'deploy',
            project_id: 'project-123',
          },
        },
      })
    })

    it('asyncOptions omits name[contains] for empty or whitespace search', async () => {
      const definition = getExecutionWorkflowFilterDefinition('project-123')

      await definition.asyncOptions!('')
      await definition.asyncOptions!('   ')

      expect(mockGet).toHaveBeenNthCalledWith(1, '/workflows', {
        params: {
          query: {
            limit: 50,
            project_id: 'project-123',
          },
        },
      })
      expect(mockGet).toHaveBeenNthCalledWith(2, '/workflows', {
        params: {
          query: {
            limit: 50,
            project_id: 'project-123',
          },
        },
      })
    })

    it('asyncOptions returns an empty list when the workflows request fails', async () => {
      mockGet.mockRejectedValueOnce(new Error('network error'))
      const definition = getExecutionWorkflowFilterDefinition('project-123')

      await expect(definition.asyncOptions!('deploy')).resolves.toEqual([])
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
