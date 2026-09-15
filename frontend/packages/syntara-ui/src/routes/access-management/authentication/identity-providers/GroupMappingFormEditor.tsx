import { ActionGroup, Button } from '@patternfly/react-core'
import type { MutableRefObject } from 'react'
import { useLayoutEffect } from 'react'
import { FormProvider } from 'react-hook-form'

import { SynPage, SynPageBody } from '../../../../components/layout/SynPage'
import { SynPageHeader } from '../../../../components/layout/SynPageHeader'
import { SynPanel } from '../../../../components/layout/SynPanel'
import { useDocLink } from '../../../../utils/docs/useDocLink'

import { GroupMappingEditPanel } from './GroupMappingEditPanel'
import { useGroupMappingEditForm, type UseGroupMappingFormMetadataResult } from './useGroupMappingForm'

type GroupMappingFormEditorProps = {
  metadata: UseGroupMappingFormMetadataResult
  openTestSignInRef: MutableRefObject<(() => void) | null>
}

function GroupMappingFormEditorContent({
  metadata,
  openTestSignInRef,
  providerId,
  config,
}: Readonly<
  GroupMappingFormEditorProps & { providerId: string; config: NonNullable<UseGroupMappingFormMetadataResult['config']> }
>) {
  const { defaultExpression, groupMappingConfig, idpType, pageTitle, breadcrumbs } = metadata
  const mappingDocLink = useDocLink('identityProviderMapping')

  const editForm = useGroupMappingEditForm({
    providerId,
    config,
    defaultExpression,
    groupMappingConfig,
    idpType,
  })

  useLayoutEffect(() => {
    openTestSignInRef.current = editForm.openTestSignIn
  }, [editForm.openTestSignIn, openTestSignInRef])

  return (
    <FormProvider {...editForm.form}>
      <SynPage>
        <SynPageHeader title={pageTitle} breadcrumbs={breadcrumbs} docLink={mappingDocLink} />
        <SynPageBody>
          <SynPanel
            isFullHeight
            isScrollable
            panelMainBodyProps={{ style: { padding: 'var(--pf-t--global--spacer--lg)' } }}
            footer={
              <ActionGroup>
                <Button
                  variant="primary"
                  onClick={editForm.onSave}
                  isLoading={editForm.isSaving}
                  isDisabled={editForm.isSaving}
                >
                  Save mapping
                </Button>
                <Button variant="link" onClick={editForm.onCancel}>
                  Cancel
                </Button>
              </ActionGroup>
            }
          >
            <GroupMappingEditPanel {...editForm.panel} />
          </SynPanel>
        </SynPageBody>
      </SynPage>
    </FormProvider>
  )
}

export function GroupMappingFormEditor({ metadata, openTestSignInRef }: Readonly<GroupMappingFormEditorProps>) {
  const { providerId, config } = metadata

  if (!providerId || !config) return null

  return (
    <GroupMappingFormEditorContent
      key={providerId}
      metadata={metadata}
      openTestSignInRef={openTestSignInRef}
      providerId={providerId}
      config={config}
    />
  )
}
