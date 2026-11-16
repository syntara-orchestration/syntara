import { DescriptionList, Flex, FlexItem, LabelGroup, Skeleton, Stack, StackItem } from '@patternfly/react-core'
import { RhUiWarningIcon } from '@patternfly/react-icons'
import type { IntegrationsAPI } from '@syntara/contracts'
import { IntegrationTypeEnum } from '@syntara/contracts'

import { AppRoute } from '../../../../app/AppRoute'
import { integrationsClient } from '../../../../client'
import { SynDetail } from '../../../../components/details/SynDetail'
import { SynLabel } from '../../../../components/labels/SynLabel'
import { SynLink } from '../../../../components/SynLink'
import { DateCell } from '../../../../components/table/DateCell'
import { INTEGRATION_TYPE_LABELS, PROVIDER_HINT_LABELS } from '../integrationFilters'
import { getBaseUrl, getProviderHint, getResourceNoun, isLLMProvider } from '../integrationUtils'
import { StatusLabel } from '../StatusLabel'

import styles from './IntegrationDetail.module.css'
import { SecuritySection } from './SecuritySection'

type IntegrationRead = IntegrationsAPI.components['schemas']['IntegrationRead']

function IntegrationProjectsList({ integrationId }: Readonly<{ integrationId: string }>) {
  const { data, isPending } = integrationsClient.useQuery('get', '/integrations/{integration_id}/projects', {
    params: { path: { integration_id: integrationId } },
  })

  if (isPending) return <Skeleton width="200px" />

  const assignments = data?.resources ?? []
  if (assignments.length === 0) return <>—</>

  return (
    <LabelGroup numLabels={5}>
      {assignments.map((a) => (
        <SynLabel key={a.project_id}>{a.project_name}</SynLabel>
      ))}
    </LabelGroup>
  )
}

export function IntegrationDetailsTab({
  integration,
  enabledResourceCount,
  credentialName,
  credentialEnabled,
}: Readonly<{
  integration: IntegrationRead
  enabledResourceCount: number
  credentialName: string | undefined
  credentialEnabled: boolean
}>) {
  const credentialId = integration.management_credential_id
  const resourceNoun = getResourceNoun(integration)

  return (
    <Stack hasGutter className={styles.tabContent}>
      <StackItem>
        <DescriptionList isHorizontal>
          <SynDetail label={isLLMProvider(integration) ? 'Name' : 'Server name / ID'}>{integration.name}</SynDetail>
          <SynDetail label="Description">{integration.description}</SynDetail>
          <SynDetail label="Integration type">
            {INTEGRATION_TYPE_LABELS[integration.integration_type ?? ''] ?? integration.integration_type ?? ''}
          </SynDetail>
          <SynDetail label="Status">
            <StatusLabel
              status={integration.validation_status ?? 'unknown'}
              errorMessage={integration.validation_error}
            />
          </SynDetail>
          <SynDetail label="Last checked">
            <DateCell dateString={integration.last_validated_at} />
          </SynDetail>
          <SynDetail label="Scope">{integration.scope === 'project' ? 'Project' : 'Global'}</SynDetail>
          {integration.scope === 'project' && integration.id && (
            <SynDetail label="Assigned projects">
              <IntegrationProjectsList integrationId={integration.id} />
            </SynDetail>
          )}
          {isLLMProvider(integration) && (
            <SynDetail label="Provider type">
              {PROVIDER_HINT_LABELS[getProviderHint(integration)] ?? getProviderHint(integration)}
            </SynDetail>
          )}
          <SynDetail label="URL">{getBaseUrl(integration) || '—'}</SynDetail>
          <SynDetail label="Connection credential">
            {!credentialId || !credentialName ? (
              <>None</>
            ) : (
              <Flex alignItems={{ default: 'alignItemsCenter' }} gap={{ default: 'gapSm' }}>
                <FlexItem>
                  <SynLink to={AppRoute.Configuration.Credentials.Detail.replace(':credentialId', credentialId)}>
                    {credentialName}
                  </SynLink>
                </FlexItem>
                {!credentialEnabled && (
                  <FlexItem>
                    <SynLabel variant="outline" status="warning" icon={<RhUiWarningIcon />}>
                      Credential disabled
                    </SynLabel>
                  </FlexItem>
                )}
              </Flex>
            )}
          </SynDetail>
          {(isLLMProvider(integration) || integration.integration_type === IntegrationTypeEnum.MCP_SERVER) && (
            <SynDetail label={`Enabled ${resourceNoun}`}>{String(enabledResourceCount)}</SynDetail>
          )}
        </DescriptionList>
      </StackItem>
      <SecuritySection configuration={integration.configuration} />
    </Stack>
  )
}
