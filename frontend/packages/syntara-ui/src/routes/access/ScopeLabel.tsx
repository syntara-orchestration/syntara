import { Button, Flex, FlexItem, LabelGroup, Stack, StackItem } from '@patternfly/react-core'
import { RhUiLockIcon } from '@patternfly/react-icons'
import { useNavigate } from '@tanstack/react-router'

import { AppRoute } from '../../app/AppRoute'
import { SynLabel } from '../../components/labels/SynLabel'
import { detachPromise } from '../../utils/detachPromise'

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
  const navigate = useNavigate()
  if (!projectId) {
    return <>-</>
  }

  const projectUrl = AppRoute.AccessManagement.ProjectDetail.replace(':projectId', projectId)

  return (
    <Button
      variant="link"
      isInline
      onClick={(e) => {
        e.stopPropagation()
        detachPromise(navigate({ to: projectUrl }))
      }}
    >
      {projectNameMap.get(projectId) ?? projectId}
    </Button>
  )
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
