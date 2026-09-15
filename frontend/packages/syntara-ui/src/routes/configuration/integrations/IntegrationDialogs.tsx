import { Badge, Content, ContentVariants } from '@patternfly/react-core'
import { IntegrationTypeEnum } from '@syntara/contracts'

import { SynConfirmationDialog } from '../../../components/dialogs/SynConfirmationDialog'

import { getResourceNoun, getTotalResourceCount, isLLMProvider } from './integrationUtils'
import type { useIntegrationActions } from './useIntegrationActions'

type IntegrationDialogsProps = Readonly<{
  validateDialog: ReturnType<typeof useIntegrationActions>['validateDialog']
  deleteDialog: ReturnType<typeof useIntegrationActions>['deleteDialog']
  disableDialog: ReturnType<typeof useIntegrationActions>['disableDialog']
  onValidate: () => void
  onDelete: () => void
  onDisable: () => void
}>

export function IntegrationDialogs({
  validateDialog,
  deleteDialog,
  disableDialog,
  onValidate,
  onDelete,
  onDisable,
}: IntegrationDialogsProps) {
  const activeItem = disableDialog.item ?? deleteDialog.item
  const hasResources =
    activeItem?.integration_type === IntegrationTypeEnum.MCP_SERVER ||
    activeItem?.integration_type === IntegrationTypeEnum.LLM_PROVIDER

  return (
    <>
      <SynConfirmationDialog
        isOpen={validateDialog.isOpen}
        onClose={validateDialog.close}
        onConfirm={onValidate}
        title="Validate integration?"
        confirmLabel="Validate"
      >
        <Content component={ContentVariants.p}>
          This will test the connection to <strong>{validateDialog.item?.name}</strong> and update its validation
          status.
        </Content>
      </SynConfirmationDialog>

      <SynConfirmationDialog
        isOpen={deleteDialog.isOpen}
        onClose={deleteDialog.close}
        onConfirm={onDelete}
        title="Delete integration?"
        confirmLabel="Delete"
        confirmVariant="danger"
        titleIconVariant="warning"
        destructiveAcknowledgement={{
          checkboxId: 'delete-integration-ack',
          label: hasResources
            ? 'I understand this integration and the resources shown above will be permanently deleted.'
            : 'I understand this integration will be permanently deleted.',
        }}
      >
        <Content component={ContentVariants.p}>
          The integration <strong>{deleteDialog.item?.name}</strong> will be deleted. This cannot be undone.
        </Content>
        {hasResources && (
          <>
            <Content component={ContentVariants.p}>
              <strong>Resources that will be deleted</strong>
            </Content>
            <Content component={ContentVariants.p}>
              {deleteDialog.item && isLLMProvider(deleteDialog.item) ? 'Models' : 'Tools'}{' '}
              <Badge isRead>{deleteDialog.item ? getTotalResourceCount(deleteDialog.item) : 0}</Badge>
            </Content>
          </>
        )}
      </SynConfirmationDialog>

      <SynConfirmationDialog
        isOpen={disableDialog.isOpen}
        onClose={disableDialog.close}
        onConfirm={onDisable}
        title="Disable integration?"
        confirmLabel="Disable"
        confirmVariant="primary"
      >
        <Content component={ContentVariants.p}>
          You are about to disable the following integration: <strong>{disableDialog.item?.name}</strong>
        </Content>
        {hasResources ? (
          <Content component={ContentVariants.p}>
            Workflows using this integration will no longer have access to its{' '}
            {disableDialog.item ? getResourceNoun(disableDialog.item) : 'tools'}. You can re-enable the integration at
            any time.
          </Content>
        ) : (
          <Content component={ContentVariants.p}>
            Workflows using this integration will no longer be able to connect to Ansible Automation Platform. You can
            re-enable the integration at any time.
          </Content>
        )}
      </SynConfirmationDialog>
    </>
  )
}
