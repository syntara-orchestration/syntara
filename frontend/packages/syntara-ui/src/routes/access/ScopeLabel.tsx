import { Flex, FlexItem, LabelGroup, Stack, StackItem } from '@patternfly/react-core'
import { RhUiLockIcon } from '@patternfly/react-icons'

import { SynLabel } from '../../components/labels/SynLabel'
import { LinkCell } from '../../components/table/LinkCell'
import { getProjectDetailPath } from '../access-management/accessManagementPaths'

import type { PolicyStatement } from './types'

const SCOPE_DISPLAY: Record<string, { label: string; color: 'blue' | 'green' | 'teal' }> = {
  system: { label: 'System', color: 'blue' },
  any: { label: 'Any', color: 'blue' },
  self: { label: 'Self', color: 'teal' },
  project: { label: 'Project', color: 'green' },
}

type ScopeLabelProps = {
  scope?: string | null
}

export function ScopeLabel({ scope }: Readonly<ScopeLabelProps>) {
  const display = SCOPE_DISPLAY[scope ?? ''] ?? SCOPE_DISPLAY.system

  return <SynLabel color={display.color}>{display.label}</SynLabel>
}

type PolicyTypeLabelProps = {
  isBuiltin?: boolean
}

export function PolicyTypeLabel({ isBuiltin }: Readonly<PolicyTypeLabelProps>) {
  if (isBuiltin) {
    return (
      <SynLabel color="grey" icon={<RhUiLockIcon />}>
        Built-in
      </SynLabel>
    )
  }
  return <SynLabel color="blue">Custom</SynLabel>
}

type ProjectLabelProps = {
  projectId?: string | null
  projectNameMap: Map<string, string>
}

export function ProjectLabel({ projectId, projectNameMap }: Readonly<ProjectLabelProps>) {
  if (!projectId) {
    return <>-</>
  }

  return <LinkCell href={getProjectDetailPath(projectId)}>{projectNameMap.get(projectId) ?? projectId}</LinkCell>
}

type StatementsCellProps = {
  statements: PolicyStatement[]
}

type StepTypeConditionLabel = {
  key: string
  text: string
}

function getStepTypeConditionLabels(stmt: PolicyStatement): StepTypeConditionLabel[] {
  if (!stmt.actions.some((action) => action.startsWith('step_type:'))) {
    return []
  }

  const labels: StepTypeConditionLabel[] = []
  for (const [condition, value] of Object.entries(stmt.conditions ?? {})) {
    if (condition !== 'resource_labels' && condition !== 'resource_labels_not') continue
    if (typeof value !== 'object' || value === null || !('kind' in value)) continue
    if (typeof value.kind !== 'string') continue

    const prefix = condition === 'resource_labels_not' ? 'Step type except' : 'Step type'
    labels.push({ key: condition, text: `${prefix}: ${value.kind}` })
  }
  return labels
}

export function StatementsCell({ statements }: Readonly<StatementsCellProps>) {
  if (statements.length === 0) {
    return <>—</>
  }

  return (
    <Stack hasGutter>
      {statements.map((stmt) => (
        <StackItem key={JSON.stringify(stmt)}>
          <Flex gap={{ default: 'gapXs' }} alignItems={{ default: 'alignItemsCenter' }} flexWrap={{ default: 'wrap' }}>
            <FlexItem>
              <SynLabel color={stmt.effect === 'allow' ? 'green' : 'red'}>
                {stmt.effect === 'allow' ? 'Allow' : 'Deny'}
              </SynLabel>
            </FlexItem>
            <FlexItem>
              <SynLabel color="grey">Scope: {stmt.scope}</SynLabel>
            </FlexItem>
            <FlexItem>
              <LabelGroup isCompact numLabels={2}>
                {stmt.actions.map((action) => (
                  <SynLabel key={action} color="grey">
                    {action}
                  </SynLabel>
                ))}
              </LabelGroup>
            </FlexItem>
            {getStepTypeConditionLabels(stmt).map(({ key, text }) => (
              <FlexItem key={key}>
                <SynLabel color="grey">{text}</SynLabel>
              </FlexItem>
            ))}
          </Flex>
        </StackItem>
      ))}
    </Stack>
  )
}
