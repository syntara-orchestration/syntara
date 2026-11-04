import type { FilterFieldDefinition } from '../../../types/filters'
import { FilterOperatorEnum, FilterTypeEnum } from '../../../types/filters'

export const getFormResponseNameFilterDefinition = (): FilterFieldDefinition => ({
  key: 'name',
  label: 'Name',
  type: FilterTypeEnum.TEXT,
  operators: [FilterOperatorEnum.CONTAINS],
  defaultOperator: FilterOperatorEnum.CONTAINS,
  placeholder: 'Filter by name',
})

export const getFormResponseStatusFilterDefinition = (): FilterFieldDefinition => ({
  key: 'status',
  label: 'Status',
  type: FilterTypeEnum.MULTISELECT,
  operators: [FilterOperatorEnum.IN],
  defaultOperator: FilterOperatorEnum.IN,
  options: [
    { value: 'pending', label: 'Pending' },
    { value: 'submitted', label: 'Submitted' },
    { value: 'expired', label: 'Expired' },
    { value: 'cancelled', label: 'Cancelled' },
  ],
  placeholder: 'Filter by status',
})
