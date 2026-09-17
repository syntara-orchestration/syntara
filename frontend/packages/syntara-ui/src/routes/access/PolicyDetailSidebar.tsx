import {
  Button,
  Content,
  ContentVariants,
  DescriptionList,
  DescriptionListDescription,
  DescriptionListGroup,
  DescriptionListTerm,
  Divider,
  Flex,
  FlexItem,
  Icon,
  Label,
  Stack,
  StackItem,
  Title,
  TitleSizes,
} from '@patternfly/react-core'
import { RhUiCloseIcon } from '@patternfly/react-icons'
import { useNavigate } from '@tanstack/react-router'
import { useEffect } from 'react'

import { AppRoute } from '../../app/AppRoute'
import { SynCodeBlock } from '../../components/details/SynCodeBlock'
import { SynPanel } from '../../components/layout/SynPanel'
import { DateCell } from '../../components/table/DateCell'
import { detachPromise } from '../../utils/detachPromise'

import { buildPolicyDefinitionJson } from './policyUtils'
import { PolicyTypeLabel } from './ScopeLabel'
import type { PolicyRead } from './types'

type PolicyDetailSidebarProps = {
  policy: PolicyRead
  onClose: () => void
  /** Resolved project name for the policy scope. Falls back to UUID if not provided. */
  projectName?: string | null
}

function ProjectScopeLink({
  projectId,
  projectName,
}: Readonly<{ projectId: string; projectName: string | null | undefined }>) {
  const navigate = useNavigate()
  return (
    <Button
      variant="link"
      isInline
      onClick={() =>
        detachPromise(navigate({ to: AppRoute.AccessManagement.ProjectDetail.replace(':projectId', projectId) }))
      }
    >
      Project: {projectName ?? projectId}
    </Button>
  )
}

export function PolicyDetailSidebar({ policy, onClose, projectName }: Readonly<PolicyDetailSidebarProps>) {
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [onClose])

  const policyJson = buildPolicyDefinitionJson(policy)

  const hasLabels = Object.keys(policy.labels ?? {}).length > 0

  return (
    <SynPanel
      style={{ width: '32rem', borderLeft: '1px solid var(--pf-t--global--border--color--default)' }}
      isFullHeight
      isScrollable
    >
      <Stack hasGutter style={{ padding: 'var(--pf-t--global--spacer--md)' }}>
        {/* Header */}
        <StackItem>
          <Flex alignItems={{ default: 'alignItemsCenter' }} justifyContent={{ default: 'justifyContentSpaceBetween' }}>
            <FlexItem>
              <Title headingLevel="h2" size={TitleSizes.lg}>
                Policy details
              </Title>
            </FlexItem>
            <FlexItem>
              <Button variant="plain" onClick={onClose} aria-label="Close policy details">
                <Icon>
                  <RhUiCloseIcon />
                </Icon>
              </Button>
            </FlexItem>
          </Flex>
        </StackItem>

        {/* Name and type */}
        <StackItem>
          <Flex alignItems={{ default: 'alignItemsCenter' }} gap={{ default: 'gapSm' }}>
            <FlexItem>
              <code style={{ fontSize: 'var(--pf-t--global--font--size--body--lg)' }}>{policy.name}</code>
            </FlexItem>
            <FlexItem>
              <PolicyTypeLabel isBuiltin={policy.is_builtin} />
            </FlexItem>
          </Flex>
        </StackItem>

        {/* Built-in notice */}
        {policy.is_builtin && (
          <StackItem>
            <Content
              component={ContentVariants.small}
              style={{ color: 'var(--pf-t--global--color--status--info--default)' }}
            >
              This is a system policy and cannot be modified.
            </Content>
          </StackItem>
        )}

        {/* Description */}
        {policy.description && (
          <StackItem>
            <Content component={ContentVariants.p}>{policy.description}</Content>
          </StackItem>
        )}

        {/* Metadata */}
        <StackItem>
          <DescriptionList isCompact>
            <DescriptionListGroup>
              <DescriptionListTerm>Scope</DescriptionListTerm>
              <DescriptionListDescription>
                {(policy.scope ?? 'any').charAt(0).toUpperCase() + (policy.scope ?? 'any').slice(1)}
              </DescriptionListDescription>
            </DescriptionListGroup>
            {policy.project_id && (
              <DescriptionListGroup>
                <DescriptionListTerm>Project</DescriptionListTerm>
                <DescriptionListDescription>
                  <ProjectScopeLink projectId={policy.project_id} projectName={projectName} />
                </DescriptionListDescription>
              </DescriptionListGroup>
            )}
            <DescriptionListGroup>
              <DescriptionListTerm>Created</DescriptionListTerm>
              <DescriptionListDescription>
                <DateCell dateString={policy.created_at} />
              </DescriptionListDescription>
            </DescriptionListGroup>
            <DescriptionListGroup>
              <DescriptionListTerm>Updated</DescriptionListTerm>
              <DescriptionListDescription>
                <DateCell dateString={policy.updated_at} />
              </DescriptionListDescription>
            </DescriptionListGroup>
            {hasLabels && (
              <DescriptionListGroup>
                <DescriptionListTerm>Labels</DescriptionListTerm>
                <DescriptionListDescription>
                  <Flex gap={{ default: 'gapSm' }} flexWrap={{ default: 'wrap' }}>
                    {Object.entries(policy.labels ?? {}).map(([key, value]) => (
                      <FlexItem key={key}>
                        <Label isCompact>
                          {key}: {String(value)}
                        </Label>
                      </FlexItem>
                    ))}
                  </Flex>
                </DescriptionListDescription>
              </DescriptionListGroup>
            )}
          </DescriptionList>
        </StackItem>

        <StackItem>
          <Divider />
        </StackItem>

        {/* Statements - structured view */}
        <StackItem>
          <Title headingLevel="h3" size={TitleSizes.md} style={{ marginBottom: 'var(--pf-t--global--spacer--sm)' }}>
            Statements
          </Title>
          {policy.statements.length === 0 ? (
            <Content component={ContentVariants.small}>No statements defined.</Content>
          ) : (
            <Stack hasGutter>
              {policy.statements.map((stmt) => (
                <StackItem key={`${stmt.effect}-${stmt.scope}-${stmt.actions.join(',')}`}>
                  <Flex
                    gap={{ default: 'gapSm' }}
                    alignItems={{ default: 'alignItemsFlexStart' }}
                    direction={{ default: 'column' }}
                  >
                    <FlexItem>
                      <Flex gap={{ default: 'gapSm' }} alignItems={{ default: 'alignItemsCenter' }}>
                        <Label color={stmt.effect === 'allow' ? 'green' : 'red'} isCompact>
                          {stmt.effect.toUpperCase()}
                        </Label>
                        <Label color="grey" isCompact>
                          scope: {stmt.scope}
                        </Label>
                      </Flex>
                    </FlexItem>
                    <FlexItem>
                      <Flex gap={{ default: 'gapXs' }} flexWrap={{ default: 'wrap' }}>
                        {stmt.actions.map((action) => (
                          <FlexItem key={action}>
                            <Label variant="outline" isCompact>
                              {action}
                            </Label>
                          </FlexItem>
                        ))}
                      </Flex>
                    </FlexItem>
                    {stmt.conditions && Object.keys(stmt.conditions).length > 0 && (
                      <FlexItem>
                        <Content
                          component={ContentVariants.small}
                          style={{ marginBottom: 'var(--pf-t--global--spacer--xs)' }}
                        >
                          Conditions:
                        </Content>
                        <SynCodeBlock jsonObject={stmt.conditions} noMaxHeight enableCopy={false} />
                      </FlexItem>
                    )}
                  </Flex>
                </StackItem>
              ))}
            </Stack>
          )}
        </StackItem>

        <StackItem>
          <Divider />
        </StackItem>

        {/* Copyable policy definition (name, description, statements) */}
        <StackItem>
          <Title headingLevel="h3" size={TitleSizes.md} style={{ marginBottom: 'var(--pf-t--global--spacer--sm)' }}>
            Policy definition
          </Title>
          <SynCodeBlock jsonObject={policyJson} noMaxHeight enableCopy />
        </StackItem>
      </Stack>
    </SynPanel>
  )
}
