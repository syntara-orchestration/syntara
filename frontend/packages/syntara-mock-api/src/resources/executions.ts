import type { Execution } from '@syntara/contracts'

import { mockDate } from './mockDates'
import { workflows } from './workflows'

const workflowNames: Record<string, string> = Object.fromEntries(workflows.map((w) => [w.id, w.name]))

const workflowIdByName: Record<string, string> = Object.fromEntries(workflows.map((w) => [w.name, w.id]))

const CONDITIONAL_DEMO = workflowIdByName['conditional-demo']
const HELLO_WORLD = workflowIdByName['hello-world']
const LOOP_DEMO = workflowIdByName['loop-demo']
const PARALLEL_DEMO = workflowIdByName['parallel-demo']
const DEPLOYMENT_APPROVAL = workflowIdByName['deployment-approval']

export const executions: Execution[] = [
  {
    id: 'exec-1',
    created_at: mockDate.daysAgo2,
    updated_at: mockDate.daysAgo2,
    workflow_id: HELLO_WORLD,
    workflow_name: workflowNames[HELLO_WORLD],
    status: 'completed',
    started_at: mockDate.daysAgo2Plus1s,
    completed_at: mockDate.daysAgo2Plus5s,
    started_by: 'user-1',
    input_data: {},
  },
  {
    id: 'exec-2',
    created_at: mockDate.daysAgo1, // 1 day ago
    updated_at: mockDate.daysAgo1,
    workflow_id: HELLO_WORLD,
    workflow_name: workflowNames[HELLO_WORLD],
    status: 'completed',
    started_at: mockDate.daysAgo1Plus1s,
    completed_at: mockDate.daysAgo1Plus3s,
    started_by: 'user-1',
    input_data: {},
  },
  {
    id: 'exec-3',
    created_at: mockDate.hoursAgo6, // 6 hours ago
    updated_at: mockDate.hoursAgo6,
    workflow_id: CONDITIONAL_DEMO,
    workflow_name: workflowNames[CONDITIONAL_DEMO],
    status: 'failed',
    started_at: mockDate.hoursAgo6Plus1s,
    completed_at: mockDate.hoursAgo6Plus2s,
    started_by: 'user-2',
    input_data: {},
    error_details: 'Task execution failed: Connection timeout',
  },
  {
    id: 'exec-4',
    created_at: mockDate.hoursAgo2, // 2 hours ago
    updated_at: mockDate.minutesAgo30, // 30 minutes ago
    workflow_id: CONDITIONAL_DEMO,
    workflow_name: workflowNames[CONDITIONAL_DEMO],
    status: 'running',
    started_at: mockDate.hoursAgo2Plus1s,
    completed_at: null,
    started_by: 'user-1',
    input_data: {},
    current_activities: [
      {
        activity_name: 'check_temperature',
        temporal_activity_id: 'activity-123',
        iteration: null,
      },
    ],
  },
  // Retry of exec-3 (failed run for conditional-demo)
  {
    id: 'exec-3-retry',
    created_at: mockDate.hoursAgo1,
    updated_at: mockDate.hoursAgo1,
    workflow_id: CONDITIONAL_DEMO,
    workflow_name: workflowNames[CONDITIONAL_DEMO],
    status: 'completed',
    started_at: mockDate.hoursAgo1,
    completed_at: mockDate.minutesAgo30,
    started_by: 'user-2',
    input_data: {},
    retried_from_execution_id: 'exec-3',
  },
  // Executions for conditional-demo
  {
    id: 'exec-5',
    created_at: mockDate.daysAgo3, // 3 days ago
    updated_at: mockDate.daysAgo3,
    workflow_id: CONDITIONAL_DEMO,
    workflow_name: workflowNames[CONDITIONAL_DEMO],
    status: 'completed',
    started_at: mockDate.daysAgo3Plus1s,
    completed_at: mockDate.daysAgo3Plus8s,
    started_by: 'user-1',
    input_data: { value: 42 },
  },
  {
    id: 'exec-6',
    created_at: mockDate.hoursAgo12, // 12 hours ago
    updated_at: mockDate.hoursAgo12,
    workflow_id: HELLO_WORLD,
    workflow_name: workflowNames[HELLO_WORLD],
    status: 'paused',
    approval_pending: false,
    started_at: mockDate.hoursAgo12Plus1s,
    completed_at: null,
    started_by: 'user-2',
    input_data: { value: 10 },
    current_activities: [
      {
        activity_name: 'say_hello',
        temporal_activity_id: 'activity-456',
        iteration: null,
      },
    ],
  },
  // Executions for loop-demo
  {
    id: 'exec-7',
    created_at: mockDate.daysAgo5, // 5 days ago
    updated_at: mockDate.daysAgo5,
    workflow_id: LOOP_DEMO,
    workflow_name: workflowNames[LOOP_DEMO],
    status: 'completed',
    started_at: mockDate.daysAgo5Plus1s,
    completed_at: mockDate.daysAgo5Plus15s,
    started_by: 'user-1',
    input_data: { items: [1, 2, 3] },
  },
  {
    id: 'exec-8',
    created_at: mockDate.hoursAgo1, // 1 hour ago
    updated_at: mockDate.hoursAgo1,
    workflow_id: LOOP_DEMO,
    workflow_name: workflowNames[LOOP_DEMO],
    status: 'cancelled',
    started_at: mockDate.hoursAgo1Plus1s,
    completed_at: mockDate.minutesAgo45, // 45 minutes ago
    started_by: 'user-3',
    input_data: { items: [1, 2, 3, 4, 5] },
  },
  // Executions for parallel-demo
  {
    id: 'exec-9',
    created_at: mockDate.daysAgo4, // 4 days ago
    updated_at: mockDate.daysAgo4,
    workflow_id: PARALLEL_DEMO,
    workflow_name: workflowNames[PARALLEL_DEMO],
    status: 'completed',
    started_at: mockDate.daysAgo4Plus1s,
    completed_at: mockDate.daysAgo4Plus12s,
    started_by: 'user-1',
    input_data: {},
  },
  {
    id: 'exec-10',
    created_at: mockDate.minutesAgo30, // 30 minutes ago
    updated_at: mockDate.minutesAgo15, // 15 minutes ago
    workflow_id: PARALLEL_DEMO,
    workflow_name: workflowNames[PARALLEL_DEMO],
    status: 'pending',
    started_at: null,
    completed_at: null,
    started_by: 'user-2',
    input_data: {},
  },
  // Execution for deployment-approval — waiting at approval gate
  {
    id: 'exec-approval',
    created_at: mockDate.minutesAgo10,
    updated_at: mockDate.minutesAgo10,
    workflow_id: DEPLOYMENT_APPROVAL,
    workflow_name: workflowNames[DEPLOYMENT_APPROVAL],
    status: 'paused',
    approval_pending: true,
    started_at: mockDate.minutesAgo10,
    completed_at: null,
    started_by: 'user-1',
    input_data: { environment: 'production', version: '3.2.0' },
    current_activities: [
      {
        activity_name: 'approval_gate',
        temporal_activity_id: 'activity-approval-gate',
        iteration: null,
      },
    ],
  },
  // Execution for deployment-approval — running with parallel branch waiting at approval
  {
    id: 'exec-parallel-approval',
    created_at: mockDate.minutesAgo30,
    updated_at: mockDate.minutesAgo15,
    workflow_id: DEPLOYMENT_APPROVAL,
    workflow_name: workflowNames[DEPLOYMENT_APPROVAL],
    status: 'running',
    approval_pending: true,
    started_at: mockDate.minutesAgo30,
    completed_at: null,
    started_by: 'user-2',
    input_data: { environment: 'staging', version: '3.1.0' },
    current_activities: [
      {
        activity_name: 'approval_gate',
        temporal_activity_id: 'activity-approval-parallel',
        iteration: null,
      },
    ],
  },
  // Execution for deployment-approval — completed with approval audit
  {
    id: 'exec-42',
    created_at: mockDate.hoursAgo3,
    updated_at: mockDate.hoursAgo3,
    workflow_id: DEPLOYMENT_APPROVAL,
    workflow_name: workflowNames[DEPLOYMENT_APPROVAL],
    status: 'completed',
    started_at: mockDate.hoursAgo3,
    completed_at: mockDate.hoursAgo2Plus1s,
    started_by: 'user-1',
    input_data: { environment: 'production', version: '3.2.0' },
  },
  // Additional executions for conditional-demo to test pagination
  // Using deterministic timestamps from mockDates to prevent visual regression baseline drift
  ...(
    [
      { hours: 7, status: 'completed' as const },
      { hours: 8, status: 'failed' as const },
      { hours: 9, status: 'running' as const },
      { hours: 10, status: 'cancelled' as const },
      { hours: 11, status: 'completed' as const },
      { hours: 13, status: 'failed' as const },
      { hours: 14, status: 'running' as const },
      { hours: 15, status: 'cancelled' as const },
      { hours: 16, status: 'completed' as const },
      { hours: 17, status: 'failed' as const },
      { hours: 18, status: 'running' as const },
      { hours: 19, status: 'cancelled' as const },
      { hours: 20, status: 'completed' as const },
      { hours: 21, status: 'failed' as const },
      { hours: 22, status: 'running' as const },
      { hours: 23, status: 'cancelled' as const },
      { hours: 24, status: 'completed' as const },
      { hours: 25, status: 'failed' as const },
      { hours: 26, status: 'running' as const },
      { hours: 27, status: 'cancelled' as const },
      { hours: 28, status: 'completed' as const },
      { hours: 29, status: 'failed' as const },
      { hours: 30, status: 'running' as const },
      { hours: 31, status: 'cancelled' as const },
      { hours: 32, status: 'completed' as const },
    ] as const
  ).map((config, i) => {
    const timeKey = `hoursAgo${config.hours}` as keyof typeof mockDate
    const created = mockDate[timeKey]
    return {
      id: `exec-paginated-${i + 1}`,
      created_at: created,
      updated_at: created,
      workflow_id: CONDITIONAL_DEMO,
      workflow_name: workflowNames[CONDITIONAL_DEMO],
      status: config.status,
      started_at: created,
      completed_at: config.status === 'running' ? null : created,
      started_by: `user-${(i % 3) + 1}`,
      input_data: { value: i * 10 },
      ...(config.status === 'running' && {
        current_activities: [
          {
            activity_name: 'check_temperature',
            temporal_activity_id: `activity-${i}`,
            iteration: null,
          },
        ],
      }),
    }
  }),
]
