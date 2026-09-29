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

export function StatementsCell({ statements }: Readonly<StatementsCellProps>) {
  if (statements.length === 0) {
    return <>—</>
  }

  return (
    <Stack hasGutter>
      {statements.map((stmt) => (
        <StackItem key={`${stmt.effect}-${stmt.scope}-${stmt.actions.join('-')}`}>
          <Flex gap={{ default: 'gapXs' }} alignItems={{ default: 'alignItemsCenter' }} flexWrap={{ default: 'wrap' }}>
            <FlexItem>
              <SynLabel color={stmt.effect === 'allow' ? 'green' : 'red'}>
                {stmt.effect === 'allow' ? 'Allow' : 'Deny'}
              </SynLabel>
            </FlexItem>
            <FlexItem>
              <SynLabel color="grey">scope: {stmt.scope}</SynLabel>
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
          </Flex>
        </StackItem>
      ))}
    </Stack>
  )
}
