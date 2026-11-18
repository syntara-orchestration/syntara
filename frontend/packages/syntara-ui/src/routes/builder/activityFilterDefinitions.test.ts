import { describe, expect, it } from 'vitest'

import { FilterOperatorEnum, FilterTypeEnum } from '../../types/filters'

import { ACTIVITY_FILTER_DEFINITIONS } from './activityFilterDefinitions'

describe('ACTIVITY_FILTER_DEFINITIONS', () => {
  it('has three filter field definitions', () => {
    expect(ACTIVITY_FILTER_DEFINITIONS).toHaveLength(3)
  })

  it('includes a keyword text filter', () => {
    const definitions = ACTIVITY_FILTER_DEFINITIONS
    const keyword = definitions.find((d) => d.key === 'name')

    expect(keyword).toBeDefined()
    expect(keyword?.label).toBe('Keyword')
    expect(keyword?.type).toBe(FilterTypeEnum.TEXT)
    expect(keyword?.defaultOperator).toBe(FilterOperatorEnum.CONTAINS)
  })

  it('includes a node type select filter with expected options', () => {
    const definitions = ACTIVITY_FILTER_DEFINITIONS
    const typeFilter = definitions.find((d) => d.key === 'type')

    expect(typeFilter).toBeDefined()
    expect(typeFilter?.label).toBe('Type')
    expect(typeFilter?.type).toBe(FilterTypeEnum.SELECT)
    expect(typeFilter?.options).toBeDefined()

    const values = typeFilter?.options?.map((o) => o.value) ?? []
    expect(values).toContain('condition')
    expect(values).toContain('loop')
    expect(values).toContain('converge')
    expect(values).toContain('switch')
    expect(values).toContain('wait')
    expect(values).toContain('script_python')
    expect(values).toContain('script_bash')
    expect(values).toContain('agentic')
    expect(values).toContain('http_request')
    expect(values).toContain('aap_job_template')
    expect(values).toContain('aap_workflow_job_template')
    expect(values).toContain('approval')
    expect(values).toContain('internal_activity')
  })

  it('includes a status select filter with all activity status values', () => {
    const definitions = ACTIVITY_FILTER_DEFINITIONS
    const statusFilter = definitions.find((d) => d.key === 'status')

    expect(statusFilter).toBeDefined()
    expect(statusFilter?.label).toBe('Status')
    expect(statusFilter?.type).toBe(FilterTypeEnum.SELECT)
    expect(statusFilter?.options).toBeDefined()

    const values = statusFilter?.options?.map((o) => o.value) ?? []
    expect(values).toContain('pending')
    expect(values).toContain('running')
    expect(values).toContain('waiting')
    expect(values).toContain('completed')
    expect(values).toContain('failed')
    expect(values).toContain('retrying')
    expect(values).toContain('skipped')
    expect(values).toContain('cancelled')
  })

  it('uses display labels for status options', () => {
    const definitions = ACTIVITY_FILTER_DEFINITIONS
    const statusFilter = definitions.find((d) => d.key === 'status')
    const completedOption = statusFilter?.options?.find((o) => o.value === 'completed')

    expect(completedOption?.label).toBe('Successful')
  })

  it('uses display labels for type options', () => {
    const definitions = ACTIVITY_FILTER_DEFINITIONS
    const typeFilter = definitions.find((d) => d.key === 'type')
    const agenticOption = typeFilter?.options?.find((o) => o.value === 'agentic')

    expect(agenticOption?.label).toBe('Task Agent')
  })
})
