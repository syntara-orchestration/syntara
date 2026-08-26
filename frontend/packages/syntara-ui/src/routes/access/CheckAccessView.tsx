import { zodResolver } from '@hookform/resolvers/zod'
import {
  Alert,
  Button,
  Content,
  ContentVariants,
  Flex,
  FlexItem,
  Form,
  FormGroup,
  Spinner,
  Stack,
  StackItem,
} from '@patternfly/react-core'
import { RhUiCheckCircleIcon, RhUiCloseCircleIcon, RhUiWarningIcon } from '@patternfly/react-icons'
import { useMemo } from 'react'
import { Controller, useForm, useWatch } from 'react-hook-form'
import { z } from 'zod'

import { SynLabel } from '../../components/labels/SynLabel'
import { SynEmptyStateNoData } from '../../components/states/SynEmptyStateNoData'
import { SynErrorState } from '../../components/states/SynErrorState'
import { getErrorMessage } from '../../utils/apiErrors'

import { accessClient } from './accessClient'
import { accessControlHelp } from './accessControlFieldHelp'
import type { ResourceActionMap } from './canIUtils'
import { ProjectSelect } from './ProjectSelect'
import { ResourceIdSelect } from './ResourceIdSelect'
import { TypeaheadSelect } from './TypeaheadSelect'
import type { CanIResponse } from './types'
import { useAllProjects } from './useAllProjects'

const checkAccessSchema = z.object({
  resourceType: z.string().min(1, 'Resource type is required'),
  action: z.string().min(1, 'Action is required'),
  resourceId: z.string().optional(),
  project: z.string().optional(),
})

type CheckAccessFormData = z.infer<typeof checkAccessSchema>

function AccessResult({
  result,
  action,
  resourceType,
  projectName,
}: Readonly<{
  result: CanIResponse
  action: string
  resourceType: string
  projectName: string
}>) {
  const projectSuffix = projectName ? (
    <>
      {' '}
      in project <strong>{projectName}</strong>
    </>
  ) : (
    <> in any project</>
  )

  if (result.allowed) {
    return (
      <Stack hasGutter>
        <StackItem>
          <Alert variant="success" title="Access allowed" isInline customIcon={<RhUiCheckCircleIcon />}>
            You can <strong>{action}</strong> on <strong>{resourceType}</strong>
            {projectSuffix}
          </Alert>
        </StackItem>
        {result.matched_policy && (
          <StackItem>
            <Content component={ContentVariants.small}>
              Matched policy: <SynLabel color="grey">{result.matched_policy}</SynLabel>
            </Content>
          </StackItem>
        )}
      </Stack>
    )
  }

  return (
    <Stack hasGutter>
      <StackItem>
        <Alert
          variant={result.denied ? 'danger' : 'warning'}
          title={result.denied ? 'Access denied' : 'Access not granted'}
          isInline
          customIcon={result.denied ? <RhUiCloseCircleIcon /> : <RhUiWarningIcon />}
        >
          You cannot <strong>{action}</strong> on <strong>{resourceType}</strong>
          {projectSuffix}
        </Alert>
      </StackItem>
      {result.denial_reason && (
        <StackItem>
          <Content component={ContentVariants.small}>Reason: {result.denial_reason}</Content>
        </StackItem>
      )}
      {result.denied_by && (
        <StackItem>
          <Content component={ContentVariants.small}>
            Denied by: <SynLabel color="grey">{result.denied_by}</SynLabel>
          </Content>
        </StackItem>
      )}
      {result.matched_policy && (
        <StackItem>
          <Content component={ContentVariants.small}>
            Matched policy: <SynLabel color="grey">{result.matched_policy}</SynLabel>
          </Content>
        </StackItem>
      )}
    </Stack>
  )
}

export function CheckAccessView({ resourceTypes, actionsByResource }: Readonly<ResourceActionMap>) {
  const { projects } = useAllProjects()

  const { control, handleSubmit, setValue, getValues } = useForm<CheckAccessFormData>({
    resolver: zodResolver(checkAccessSchema, undefined, { mode: 'sync' }),
    defaultValues: { resourceType: '', action: '', resourceId: '', project: '' },
  })

  const resourceType = useWatch({ control, name: 'resourceType', defaultValue: '' })

  const availableActions = useMemo(
    () => (resourceType ? (actionsByResource.get(resourceType) ?? []) : []),
    [resourceType, actionsByResource]
  )

  const resetDependentFields = (newResourceType: string) => {
    const actions = actionsByResource.get(newResourceType) ?? []
    const currentAction = getValues('action')
    if (actions.length === 1) {
      setValue('action', actions[0])
    } else if (!actions.includes(currentAction)) {
      setValue('action', '')
    }
    setValue('resourceId', '')
  }

  const canIMutation = accessClient.useMutation('post', '/authz/can_i')

  const onSubmit = handleSubmit((formData) => {
    canIMutation.mutate({
      body: {
        action: formData.action.trim(),
        resource_type: formData.resourceType.trim(),
        ...(formData.resourceId?.trim() && { resource_id: formData.resourceId.trim() }),
        ...(formData.project?.trim() && { resource_project: formData.project.trim() }),
      },
    })
  })

  const action = useWatch({ control, name: 'action', defaultValue: '' })

  return (
    <Flex direction={{ default: 'row' }} gap={{ default: 'gapXl' }} alignItems={{ default: 'alignItemsFlexStart' }}>
      <FlexItem style={{ minWidth: 340, maxWidth: 400 }}>
        <Form onSubmit={onSubmit}>
          <FormGroup
            label="Resource type"
            isRequired
            fieldId="can-i-resource-type"
            labelHelp={accessControlHelp.resourceType}
          >
            <Controller
              name="resourceType"
              control={control}
              render={({ field }) => (
                <TypeaheadSelect
                  id="can-i-resource-type"
                  ariaLabel="Resource type"
                  options={resourceTypes.map((rt) => ({ value: rt, label: rt }))}
                  selected={field.value}
                  onChange={(value) => {
                    field.onChange(value)
                    resetDependentFields(value)
                  }}
                  placeholder="Select a resource type"
                />
              )}
            />
          </FormGroup>

          <FormGroup label="Action" isRequired fieldId="can-i-action" labelHelp={accessControlHelp.action}>
            <Controller
              name="action"
              control={control}
              render={({ field }) => (
                <TypeaheadSelect
                  id="can-i-action"
                  ariaLabel="Action"
                  options={availableActions.map((a) => ({ value: a, label: a }))}
                  selected={field.value}
                  onChange={field.onChange}
                  placeholder={resourceType ? 'Select an action' : 'Select a resource type first'}
                  isDisabled={!resourceType}
                />
              )}
            />
          </FormGroup>

          <FormGroup label="Project" fieldId="can-i-project" labelHelp={accessControlHelp.project}>
            <Controller
              name="project"
              control={control}
              render={({ field }) => (
                <ProjectSelect
                  id="can-i-project"
                  value={field.value ?? ''}
                  onChange={field.onChange}
                  projects={projects}
                />
              )}
            />
          </FormGroup>

          <FormGroup label="Resource ID" fieldId="can-i-resource-id" labelHelp={accessControlHelp.resourceId}>
            <Controller
              name="resourceId"
              control={control}
              render={({ field }) => (
                <ResourceIdSelect resourceType={resourceType} value={field.value ?? ''} onChange={field.onChange} />
              )}
            />
          </FormGroup>

          <Button
            variant="primary"
            type="submit"
            isDisabled={!resourceType.trim() || !action.trim()}
            isLoading={canIMutation.isPending}
          >
            Check Access
          </Button>
        </Form>
      </FlexItem>

      <FlexItem grow={{ default: 'grow' }}>
        <Stack hasGutter>
          {canIMutation.isIdle && (
            <StackItem>
              <SynEmptyStateNoData
                title="Check access permissions"
                description="Select a resource type and action, then click Check Access to verify your permissions."
              />
            </StackItem>
          )}

          {canIMutation.isPending && (
            <StackItem>
              <Flex
                justifyContent={{ default: 'justifyContentCenter' }}
                style={{ padding: 'var(--pf-t--global--spacer--2xl)' }}
              >
                <Spinner size="lg" aria-label="Checking access" />
              </Flex>
            </StackItem>
          )}

          {canIMutation.isError && (
            <StackItem>
              <SynErrorState
                title="Access check failed"
                message={getErrorMessage(canIMutation.error)}
                onRetry={onSubmit}
              />
            </StackItem>
          )}

          {canIMutation.data && canIMutation.variables && (
            <AccessResult
              result={canIMutation.data}
              action={canIMutation.variables.body.action}
              resourceType={canIMutation.variables.body.resource_type}
              projectName={canIMutation.variables.body.resource_project ?? ''}
            />
          )}
        </Stack>
      </FlexItem>
    </Flex>
  )
}
