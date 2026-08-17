import { ActionGroup, Button } from '@patternfly/react-core'
import type { MutableRefObject } from 'react'
import { useLayoutEffect } from 'react'
import { FormProvider } from 'react-hook-form'

import { NxPage, NxPageBody } from '../../../../components/layout/NxPage'
import { NxPageHeader } from '../../../../components/layout/NxPageHeader'
import { NxPanel } from '../../../../components/layout/NxPanel'
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
      <NxPage>
        <NxPageHeader title={pageTitle} breadcrumbs={breadcrumbs} docLink={mappingDocLink} />
        <NxPageBody>
          <NxPanel
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
          </NxPanel>
        </NxPageBody>
      </NxPage>
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
