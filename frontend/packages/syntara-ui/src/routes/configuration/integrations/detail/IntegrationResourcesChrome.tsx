import { ActionGroup, Badge, Button } from '@patternfly/react-core'
import type { IntegrationsAPI } from '@syntara/contracts'

import { getTotalResourceCount } from '../integrationUtils'

type IntegrationRead = IntegrationsAPI.components['schemas']['IntegrationRead']

export function ResourcesFooter({
  isDirty,
  isSaving,
  onSave,
  saveLabel = 'Save tools',
}: Readonly<{ isDirty: boolean; isSaving: boolean; onSave: () => void; saveLabel?: string }>) {
  return (
    <ActionGroup>
      <Button variant="primary" onClick={isDirty ? onSave : undefined} isAriaDisabled={!isDirty} isLoading={isSaving}>
        {saveLabel}
      </Button>
    </ActionGroup>
  )
}

export function ResourcesTabTitle({
  integration,
  enabledResourceCount,
}: Readonly<{ integration: IntegrationRead; enabledResourceCount: number }>) {
  return <>Enabled resources {getTotalResourceCount(integration) > 0 && <Badge isRead>{enabledResourceCount}</Badge>}</>
}
