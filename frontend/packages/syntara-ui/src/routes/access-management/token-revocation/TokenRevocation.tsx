import {
  Button,
  Card,
  CardBody,
  Content,
  DescriptionList,
  DescriptionListDescription,
  DescriptionListGroup,
  DescriptionListTerm,
  Stack,
  StackItem,
} from '@patternfly/react-core'

import { adminClient } from '../../../client'
import { SynConfirmationDialog } from '../../../components/dialogs/SynConfirmationDialog'
import { DisabledWithTooltip } from '../../../components/DisabledWithTooltip'
import { useQueryState } from '../../../components/states/useQueryState'
import { DateCell } from '../../../components/table/DateCell'
import { permissionTooltip } from '../../../hooks/permissionUtils'
import { useCanI } from '../../../hooks/useCanI'
import { useDialogState } from '../../../hooks/useDialogState'
import { useMutationErrorHandler } from '../../../hooks/useMutationErrorHandler'
import { useAlerts } from '../../../providers/alerts'
import { useAuthStore } from '../../../stores/useAuthStore'
import { detachPromise } from '../../../utils/detachPromise'

export function TokenRevocationTab() {
  const confirmDialog = useDialogState()
  const { showSuccess } = useAlerts()
  const handleMutationError = useMutationErrorHandler()
  const { allowed: canRevoke } = useCanI('execute', 'admin:revocation')

  const query = adminClient.useQuery('get', '/admin/revocation')
  const { mutate: revokeAll, isPending } = adminClient.useMutation('post', '/admin/revocation')

  const queryState = useQueryState(query, {
    title: 'Error loading revocation status',
    onRetry: () => detachPromise(query.refetch()),
  })
  if (queryState) return queryState

  const { revoked_before, updated_at } = query.data ?? { revoked_before: null, updated_at: null }

  const handleRevoke = () => {
    revokeAll(
      {},
      {
        onSuccess: () => {
          showSuccess({
            title: 'Tokens revoked',
            description: 'All tokens have been revoked. You will be signed out.',
          })
          confirmDialog.close()
          // Auto-logout after global revocation since the admin's own tokens are now invalid
          detachPromise(useAuthStore.getState().logout())
        },
        onError: (error) => {
          confirmDialog.close()
          handleMutationError({ title: 'Failed to revoke tokens' })(error)
        },
      }
    )
  }

  return (
    <>
      <Card>
        <CardBody>
          <Stack hasGutter>
            <StackItem>
              <DescriptionList isHorizontal>
                <DescriptionListGroup>
                  <DescriptionListTerm>Tokens revoked before</DescriptionListTerm>
                  <DescriptionListDescription>
                    {revoked_before ? (
                      <DateCell dateString={revoked_before} />
                    ) : (
                      'No global revocation has been performed'
                    )}
                  </DescriptionListDescription>
                </DescriptionListGroup>
                <DescriptionListGroup>
                  <DescriptionListTerm>Last updated</DescriptionListTerm>
                  <DescriptionListDescription>
                    {updated_at ? <DateCell dateString={updated_at} /> : 'N/A'}
                  </DescriptionListDescription>
                </DescriptionListGroup>
              </DescriptionList>
            </StackItem>
            <StackItem>
              <Content component="p">
                Revoking all tokens will immediately invalidate every active session across the platform, signing out
                all users including yourself. Use this action when a security incident requires forcing all users to
                re-authenticate.
              </Content>
            </StackItem>
            <StackItem>
              <DisabledWithTooltip
                isDisabled={!canRevoke}
                content={permissionTooltip('revoke all tokens', 'admin:revocation:execute')}
              >
                <Button
                  variant="danger"
                  onClick={() => confirmDialog.open(undefined)}
                  isLoading={isPending}
                  isAriaDisabled={!canRevoke}
                >
                  Revoke all tokens
                </Button>
              </DisabledWithTooltip>
            </StackItem>
          </Stack>
        </CardBody>
      </Card>
      <SynConfirmationDialog
        isOpen={confirmDialog.isOpen}
        onClose={confirmDialog.close}
        onConfirm={handleRevoke}
        title="Revoke all tokens?"
        confirmLabel="Revoke all tokens"
        confirmVariant="danger"
        titleIconVariant="warning"
        destructiveAcknowledgement={{
          checkboxId: 'revoke-all-tokens-ack',
          label: 'I understand all users will be signed out immediately.',
        }}
      >
        <Stack hasGutter>
          <StackItem>This will immediately invalidate every active session across the platform.</StackItem>
          <StackItem>
            <strong>You will be signed out and must sign in again.</strong>
          </StackItem>
        </Stack>
      </SynConfirmationDialog>
    </>
  )
}
