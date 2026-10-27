import { ActionGroup, Button, Form, Stack } from '@patternfly/react-core'
import { RhUiAddIcon } from '@patternfly/react-icons'
import { IntegrationTypeEnum } from '@syntara/contracts'
import { useNavigate } from '@tanstack/react-router'

import { AppRoute } from '../../app/AppRoute'
import { breadcrumbsConfigureExecutionTarget } from '../../app/breadcrumbBuilders'
import { executionPlaneClient, integrationsClient } from '../../client'
import { SynForm } from '../../components/forms/SynForm'
import { SynPage, SynPageBody } from '../../components/layout/SynPage'
import { SynPageHeader } from '../../components/layout/SynPageHeader'
import { SynPanel } from '../../components/layout/SynPanel'
import { SynPageTitle } from '../../components/SynPageTitle'
import { useDirtyFormGuard } from '../../hooks/useDirtyFormGuard'
import { useFormMutationErrorHandler } from '../../hooks/useFormMutationErrorHandler'
import { useSynForm } from '../../hooks/useSynForm'
import { useAlerts } from '../../providers/alerts'
import { detachPromise } from '../../utils/detachPromise'
import { useDocLink } from '../../utils/docs/useDocLink'

import { CreateExecutionTargetFields } from './CreateExecutionTargetFields'
import {
  EXECUTION_TARGET_FORM_DEFAULT_VALUES,
  executionTargetFormSchema,
  toExecutionTargetCreateBody,
  type ExecutionTargetFormData,
} from './executionTargetFormSchema'

const PAGE_TITLE = 'Configure execution target'

export function CreateExecutionTarget() {
  const navigate = useNavigate()
  const docLink = useDocLink('executionPlane')
  const { showAlert } = useAlerts()

  const clusterQuery = integrationsClient.useQuery('get', '/integrations', {
    params: {
      query: {
        integration_type: IntegrationTypeEnum.OPENSHIFT,
        limit: 1,
        include_total: true,
      },
    },
  })

  const openshiftIntegrations = clusterQuery.data?.resources
  const clusterName =
    openshiftIntegrations?.length === 1 ? openshiftIntegrations[0]?.name?.trim() || undefined : undefined

  const form = useSynForm({
    schema: executionTargetFormSchema,
    defaultValues: EXECUTION_TARGET_FORM_DEFAULT_VALUES,
  })
  const {
    handleSubmit,
    setError,
    reset,
    formState: { isDirty },
  } = form

  const navigateBack = () => detachPromise(navigate({ to: AppRoute.ExecutionPlane.Root }))

  const { dismiss } = useDirtyFormGuard({
    isDirty,
    onDiscard: () => reset(),
    title: 'Discard unsaved changes?',
    body: 'You have unsaved changes to this execution target. Your changes will be lost if you leave.',
  })

  const handleError = useFormMutationErrorHandler<ExecutionTargetFormData>(setError)
  const { mutate: createTarget, isPending: isSaving } = executionPlaneClient.useMutation(
    'post',
    '/api/execution_plane/v1/execution_targets'
  )

  const onSubmit = (formData: ExecutionTargetFormData) => {
    const context = formData.name ? `Execution target "${formData.name}"` : undefined
    createTarget(
      { body: toExecutionTargetCreateBody(formData) },
      {
        onSuccess: (created) => {
          dismiss()
          showAlert({ title: 'Execution target configured', variant: 'success', autoDismiss: true })
          detachPromise(
            navigate({
              to: AppRoute.ExecutionPlane.Detail.replace(':executionTargetId', created.id),
            })
          )
        },
        onError: handleError({ title: 'Failed to configure execution target', context }),
      }
    )
  }

  return (
    <SynPage>
      <SynPageTitle segments={[PAGE_TITLE, 'Execution Plane']} />
      <SynPageHeader title={PAGE_TITLE} docLink={docLink} breadcrumbs={breadcrumbsConfigureExecutionTarget()} />
      <SynPageBody>
        <SynPanel
          isFullHeight
          isScrollable
          footer={
            <ActionGroup>
              <Button
                type="submit"
                form="execution-target-create-form"
                isLoading={isSaving}
                isDisabled={isSaving}
                icon={<RhUiAddIcon />}
              >
                Configure execution target
              </Button>
              <Button variant="link" onClick={navigateBack} isDisabled={isSaving}>
                Cancel
              </Button>
            </ActionGroup>
          }
          panelMainBodyProps={{ style: { padding: 'var(--pf-t--global--spacer--xl)' } }}
        >
          <Stack style={{ maxWidth: '600px' }}>
            <Form id="execution-target-create-form" onSubmit={handleSubmit(onSubmit)}>
              <SynForm form={form}>
                <CreateExecutionTargetFields clusterName={clusterName} isClusterPending={clusterQuery.isPending} />
              </SynForm>
            </Form>
          </Stack>
        </SynPanel>
      </SynPageBody>
    </SynPage>
  )
}
