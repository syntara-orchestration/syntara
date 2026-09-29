import type { FilterFieldDefinition } from '../../types/filters'
import { FilterOperatorEnum, FilterTypeEnum } from '../../types/filters'
import { executorMetadata, nodeMetadata } from '../workflows/canvas/nodes/nodeMetadata'

import { activityStatusDisplayLabels } from './executionStatusConstants'

const ACTIVITY_STATUS_OPTIONS = Object.entries(activityStatusDisplayLabels).map(([value, label]) => ({
  value,
  label,
}))

const ACTIVITY_NODE_TYPES = ['condition', 'loop', 'converge', 'switch', 'wait'] as const
const ACTIVITY_EXECUTOR_TYPES = [
  'script',
  'agentic',
  'http_request',
  'aap_job_template',
  'aap_workflow_job_template',
  'approval',
  'internal_activity',
] as const

const NODE_TYPE_OPTIONS = [
  ...ACTIVITY_NODE_TYPES.map((key) => ({ value: key, label: nodeMetadata[key].label })),
  ...ACTIVITY_EXECUTOR_TYPES.map((key) => ({ value: key, label: executorMetadata[key].label })),
]

export const ACTIVITY_FILTER_DEFINITIONS: FilterFieldDefinition[] = [
  {
    key: 'name',
    label: 'Keyword',
    type: FilterTypeEnum.TEXT,
    operators: [FilterOperatorEnum.CONTAINS],
    defaultOperator: FilterOperatorEnum.CONTAINS,
    placeholder: 'Filter by keyword',
  },
  {
    key: 'type',
    label: 'Type',
    type: FilterTypeEnum.SELECT,
    options: NODE_TYPE_OPTIONS,
    placeholder: 'Filter by type',
  },
  {
    key: 'status',
    label: 'Status',
    type: FilterTypeEnum.SELECT,
    options: ACTIVITY_STATUS_OPTIONS,
    placeholder: 'Filter by status',
  },
]
