import {
  RhUiLanguageIcon,
  RhUiRobotIcon,
  RhUiMergeNodesIcon,
  RhUiCodeIcon,
  RhUiCalendarIcon,
  RhUiPlayIcon,
  RhUiPlugFillIcon,
  RhUiConditionNodeIcon,
  RhUiLoopNodeIcon,
  RhUiUserCheckIcon,
  RhUiTreeViewIcon,
  RhUiClockIcon,
  RhUiSettingsIcon,
} from '@patternfly/react-icons'
import type { ComponentType } from 'react'

import AnsibleIcon from '../../../../assets/ansible-automation-platform.svg?react'
import EdaIcon from '../../../../assets/eda.svg?react'

export type NodeMetadata = {
  icon?: ComponentType<{ className?: string }>
  label: string
  className?: string
  disableTarget?: boolean
  enableEnd?: boolean
  enableStart?: boolean
  expandable?: boolean
}

export const nodeMetadata: Record<string, NodeMetadata> = {
  trigger: {
    icon: RhUiPlayIcon,
    label: 'Trigger',
    disableTarget: true,
    expandable: false,
  },
  scheduledTrigger: {
    icon: RhUiCalendarIcon,
    label: 'Trigger',
    disableTarget: true,
    expandable: false,
  },
  webhookTrigger: {
    icon: RhUiLanguageIcon,
    label: 'Trigger',
    disableTarget: true,
    expandable: false,
  },
  edaTrigger: {
    icon: EdaIcon,
    label: 'Trigger',
    disableTarget: true,
    expandable: false,
  },
  task: {
    label: 'Task',
    expandable: true,
  },
  condition: {
    icon: RhUiConditionNodeIcon,
    label: 'Condition',
    expandable: false,
  },
  loop: {
    icon: RhUiLoopNodeIcon,
    label: 'Loop',
    enableEnd: true,
    expandable: false,
  },
  converge: {
    icon: RhUiMergeNodesIcon,
    label: 'Converge',
    expandable: false,
  },
  switch: {
    icon: RhUiTreeViewIcon,
    label: 'Switch',
    expandable: false,
  },
  wait: {
    icon: RhUiClockIcon,
    label: 'Wait',
    expandable: false,
  },
  /** Canvas Approval node (task executor); separate from `task` so expandable can be false. */
  approval: {
    icon: RhUiUserCheckIcon,
    label: 'Approval',
    expandable: false,
  },
}

type ExecutorDisplayMetadata = { icon: ComponentType<{ className?: string }>; label: string }

/** Same display as API executor `aap_job_template`; shared with internal `aap` from detectTaskNodeType. */
const aapJobExecutorDisplay: ExecutorDisplayMetadata = { icon: AnsibleIcon, label: 'AAP Job' }

/** Display for API executor `aap_workflow_job_template` */
const aapWorkflowExecutorDisplay: ExecutorDisplayMetadata = { icon: AnsibleIcon, label: 'AAP Workflow' }

// Task executor metadata - different tasks have different icons
export const executorMetadata: Record<string, ExecutorDisplayMetadata> = {
  script: { icon: RhUiCodeIcon, label: 'Script' },
  agentic: { icon: RhUiRobotIcon, label: 'Task Agent' },
  http_request: { icon: RhUiPlugFillIcon, label: 'REST API' },
  aap_job_template: aapJobExecutorDisplay,
  aap_workflow_job_template: aapWorkflowExecutorDisplay,
  /** Internal key from detectTaskNodeType (agentic + ansible connector prompt), not an API executor string */
  aap: aapJobExecutorDisplay,
  approval: { icon: RhUiUserCheckIcon, label: 'Approval' },
  internal_activity: { icon: RhUiSettingsIcon, label: 'System' },
}
